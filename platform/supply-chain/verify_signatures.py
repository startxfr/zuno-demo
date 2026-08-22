#!/usr/bin/env python3
"""ADR-0115/ADR-0420 policy-as-code check: "signature verification is
exercised as part of trusted promotion/deployment." Walks every
`gitops/charts/*/values.yaml` for first-party image references (anything
published under the internal `image-registry...svc:5000/zuno-ai-build/`
registry - what every chart actually deploys, per RELEASING.md), resolves
each one's LIVE `ImageStreamTag` digest (`oc get istag`), and runs
`cosign verify --key` against it using the committed Vault Transit public
key (`platform/supply-chain/keys/zuno-platform-signer.pub`) - not a
keyless GitHub OIDC identity.

Resolving the live digest rather than expecting an already-pinned one in
`values.yaml` is deliberate: every chart still declares `tag: latest`
(ADR-0115 gap 2, tracked by check_no_latest_tags.py, not solved here), but
`:latest` is a moving `ImageStreamTag`, not a moving image - at any given
moment it resolves to one real, signable digest. This check verifies
*that* digest, so it is meaningful today even though gap 2 (an immutable
tag literally written into `values.yaml`) remains open.

Needs a live cluster (`oc get istag`) and a `cosign` binary on PATH -
cannot run in GitHub Actions, which has no route to the internal registry
(same reason `.github/workflows/build-publish.yml`'s own signing steps
were removed, ADR-0420/WP-070). Run as an in-cluster check instead of a
CI lint step.

Run from the repository root, logged in to the target cluster (`oc login`):

    python3 platform/supply-chain/verify_signatures.py
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, List, Optional

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# What every chart actually deploys (RELEASING.md): the in-cluster
# BuildConfig/ImageStream path, not quay.io - no gitops/charts/*/values.yaml
# references quay.io for a first-party image today.
FIRST_PARTY_REGISTRY_PREFIX = "image-registry.openshift-image-registry.svc:5000/zuno-ai-build/"
BUILD_NAMESPACE = "zuno-ai-build"

DEFAULT_PUBLIC_KEY_PATH = REPO_ROOT / "platform" / "supply-chain" / "keys" / "zuno-platform-signer.pub"

IGNORED_TAG_VALUES = {""}


@dataclass
class ImageRef:
    file: str
    path: str
    image: str  # "quay.io/zuno/<name>:<tag>"


@dataclass
class Finding:
    message: str


def _walk(node: Any, path: str, refs: List[ImageRef], file_label: str) -> None:
    """Same shape-agnostic walk as check_no_latest_tags.py: any dict
    carrying sibling `repository`/`tag` keys is a candidate image
    reference, wherever it's nested (image.*, images.<x>.*, etc.)."""
    if isinstance(node, dict):
        repository = node.get("repository")
        tag = node.get("tag")
        if isinstance(repository, str) and isinstance(tag, str):
            if repository.startswith(FIRST_PARTY_REGISTRY_PREFIX) and tag not in IGNORED_TAG_VALUES:
                refs.append(ImageRef(file_label, path, f"{repository}:{tag}"))
        for key, value in node.items():
            _walk(value, f"{path}.{key}" if path else str(key), refs, file_label)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk(item, f"{path}[{i}]", refs, file_label)


def _collect_first_party_refs() -> List[ImageRef]:
    refs: List[ImageRef] = []
    for values_path in sorted((REPO_ROOT / "gitops" / "charts").glob("*/values.yaml")):
        doc = yaml.safe_load(values_path.read_text()) or {}
        _walk(doc, "", refs, str(values_path.relative_to(REPO_ROOT)))
    return refs


def _cosign_path() -> Optional[str]:
    return shutil.which("cosign")


def _resolve_live_digest(image: str) -> str:
    """Resolves the ImageStreamTag `<name>:<tag>` component of `image`
    (`<registry>/zuno-ai-build/<name>:<tag>`) to the real digest it
    currently points to. Raises RuntimeError on any failure (missing `oc`,
    not logged in, tag doesn't exist) - the caller reports this as a
    finding, same as a cosign failure."""
    oc_bin = shutil.which("oc")
    if oc_bin is None:
        raise RuntimeError("'oc' binary not found on PATH - cannot resolve a live ImageStreamTag digest")

    istag = image.rsplit("/", 1)[-1]  # "<name>:<tag>"
    result = subprocess.run(
        [oc_bin, "get", "istag", istag, "-n", BUILD_NAMESPACE, "-o", "jsonpath={.image.metadata.name}"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    digest = result.stdout.strip()
    if result.returncode != 0 or not digest:
        detail = (result.stderr or result.stdout or "no output").strip()
        raise RuntimeError(f"could not resolve ImageStreamTag {istag} in {BUILD_NAMESPACE}: {detail}")
    return digest


def _verify_one(cosign_bin: str, public_key: pathlib.Path, ref: "ImageRef") -> Optional[str]:
    """Returns None on success, an error message on failure. Never raises -
    a registry/cluster problem is reported as a finding, not a crash."""
    repository = ref.image.rsplit(":", 1)[0]
    try:
        digest = _resolve_live_digest(ref.image)
    except RuntimeError as exc:
        return str(exc)

    image_at_digest = f"{repository}@{digest}"
    try:
        # Unlike `cosign sign-blob`/`verify-blob` (which default to
        # touching Rekor unless told --tlog-upload=false/
        # --insecure-ignore-tlog=true), plain `cosign sign`/`verify` for
        # OCI images gate transparency-log use behind an opt-in
        # COSIGN_EXPERIMENTAL=1 env var instead - simply not setting it
        # (never set anywhere in this repo) is the whole story here.
        result = subprocess.run(
            [
                cosign_bin,
                "verify",
                "--key",
                str(public_key),
                image_at_digest,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return f"cosign verify timed out for {image_at_digest}"
    except OSError as exc:
        return f"failed to run cosign for {image_at_digest}: {exc}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "no output").strip().splitlines()[-1:]
        return f"signature verification failed for {image_at_digest}: {'; '.join(detail) or 'unknown error'}"
    return None


def main() -> int:
    refs = _collect_first_party_refs()

    print(
        f"Scanned gitops/charts/*/values.yaml for first-party image references "
        f"under {FIRST_PARTY_REGISTRY_PREFIX}, resolving each to its live ImageStreamTag digest."
    )
    if not refs:
        print("\nRESULT: PASS - no first-party image reference found. Nothing to verify.")
        return 0

    cosign_bin = _cosign_path()
    if cosign_bin is None:
        print(
            f"\n{len(refs)} image reference(s) found, but no `cosign` binary is on PATH to verify them with:"
        )
        for ref in refs:
            print(f"  ? {ref.file}: {ref.path} = {ref.image!r}")
        print("\nRESULT: FAIL - install cosign to actually verify these signatures.")
        return 1

    if not DEFAULT_PUBLIC_KEY_PATH.is_file():
        print(f"\nRESULT: FAIL - trust anchor not found at {DEFAULT_PUBLIC_KEY_PATH} (see WP-068).")
        return 1

    findings: List[Finding] = []
    for ref in refs:
        print(f"Verifying {ref.image} (from {ref.file}: {ref.path}) ...")
        error = _verify_one(cosign_bin, DEFAULT_PUBLIC_KEY_PATH, ref)
        if error:
            findings.append(Finding(error))

    if not findings:
        print(f"\nRESULT: PASS - all {len(refs)} first-party image(s) verified against {DEFAULT_PUBLIC_KEY_PATH.name}.")
        return 0

    print(f"\n{len(findings)} signature verification failure(s):")
    for f in findings:
        print(f"  ✗ {f.message}")
    print(
        "\nRESULT: FAIL - a first-party image did not verify against "
        f"{DEFAULT_PUBLIC_KEY_PATH.name}."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
