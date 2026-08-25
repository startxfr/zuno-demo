#!/usr/bin/env python3
"""ADR-0115/ADR-0420 policy-as-code check: "signature verification is
exercised as part of trusted promotion/deployment." Walks every
`gitops/charts/*/values.yaml` for first-party image references (anything
published under the internal `image-registry...svc:5000/zuno-ai-build/`
registry - what every chart actually deploys, per RELEASING.md), resolves
each one's LIVE `ImageStreamTag` digest (`oc get istag`), and runs
`cosign verify --key` against it using the committed Vault Transit public
key (`agents/zuno-platform-signer.pub`) - not a keyless GitHub OIDC
identity.

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

`--list-refs` prints the scanned/resolved refs as JSON instead of
verifying them (no `cosign` needed) - ADR-0420/WP-070's `make d2 check
supply-chain` gate uses this from the ansible controller (which has
cluster API access but, unlike a pod, no route to the internal registry
for the actual `cosign verify` pull) to hand a resolved ref list to an
in-cluster Job that does the real verification:

    python3 platform/supply-chain/verify_signatures.py --list-refs
"""
from __future__ import annotations

import argparse
import json
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

DEFAULT_PUBLIC_KEY_PATH = REPO_ROOT / "agents" / "zuno-platform-signer.pub"

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
    """Same shape-agnostic walk as check_no_latest_tags.py, extended for a
    second shape this repo actually uses: every per-agent chart (tekos,
    comage, advantage, finage, arkos, naveo) shares one agent-bff/
    agent-frontend build under `image: {registry, frontendRepository,
    bffRepository, tag}` - separate `registry`/`*Repository` fields, not
    one `repository` field - which the original `repository`/`tag`-only
    match silently never saw at all (confirmed live: without this, the
    scan finds 11 first-party images, not 13 - agent-bff/agent-frontend
    invisible to every chart that deploys them)."""
    if isinstance(node, dict):
        repository = node.get("repository")
        tag = node.get("tag")
        if isinstance(repository, str) and isinstance(tag, str):
            if repository.startswith(FIRST_PARTY_REGISTRY_PREFIX) and tag not in IGNORED_TAG_VALUES:
                refs.append(ImageRef(file_label, path, f"{repository}:{tag}"))

        registry = node.get("registry")
        if isinstance(registry, str) and isinstance(tag, str) and tag not in IGNORED_TAG_VALUES:
            for repo_key in ("frontendRepository", "bffRepository"):
                repo_suffix = node.get(repo_key)
                if isinstance(repo_suffix, str):
                    full_repository = f"{registry}/{repo_suffix}"
                    if full_repository.startswith(FIRST_PARTY_REGISTRY_PREFIX):
                        refs.append(ImageRef(file_label, f"{path}.{repo_key}", f"{full_repository}:{tag}"))

        for key, value in node.items():
            _walk(value, f"{path}.{key}" if path else str(key), refs, file_label)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk(item, f"{path}[{i}]", refs, file_label)


def _has_build_config(name: str) -> bool:
    """True iff zuno-ai-build has a BuildConfig named `name` - the actual
    distinguishing signal between a genuinely first-party image (built by
    an ansible/roles/*_build role) and a third-party image ansible/roles/
    image_mirrors happens to mirror into the SAME registry/namespace
    (e.g. vault, bitnami-kubectl - matched by FIRST_PARTY_REGISTRY_PREFIX
    on hostname alone, but never built or signed by this pipeline). Not
    every mirrored image collides with a first-party name, but any that do
    would otherwise be reported as an unsigned "first-party" image
    forever, a false positive this check must not raise."""
    oc_bin = shutil.which("oc")
    if oc_bin is None:
        return False
    result = subprocess.run(
        [oc_bin, "get", "buildconfig", name, "-n", BUILD_NAMESPACE, "-o", "name"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.returncode == 0


def _collect_first_party_refs() -> List[ImageRef]:
    """Deduplicates by `.image` (repository:tag) - agent-bff/agent-frontend
    are each declared identically in every per-agent chart (tekos, comage,
    advantage, finage, arkos, naveo all share the one build), so a naive
    walk would report - and re-verify - the same underlying image once per
    chart. The first chart alphabetically wins the `file`/`path` label."""
    refs: List[ImageRef] = []
    for values_path in sorted((REPO_ROOT / "gitops" / "charts").glob("*/values.yaml")):
        doc = yaml.safe_load(values_path.read_text()) or {}
        _walk(doc, "", refs, str(values_path.relative_to(REPO_ROOT)))

    deduped: dict = {}
    for ref in refs:
        deduped.setdefault(ref.image, ref)

    return [ref for ref in deduped.values() if _has_build_config(ref.image.rsplit("/", 1)[-1].rsplit(":", 1)[0])]


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


def _resolve_ref_dict(ref: "ImageRef") -> dict:
    """name/repository/digest triple for --list-refs JSON output - the
    exact shape ansible/tasks/verify_image_signatures.yml hands to the
    in-cluster verify Job. Raises RuntimeError (via _resolve_live_digest)
    on failure; the caller decides how to report that."""
    repository = ref.image.rsplit(":", 1)[0]
    name = repository.rsplit("/", 1)[-1]
    digest = _resolve_live_digest(ref.image)
    return {"name": name, "repository": repository, "digest": digest}


def list_refs() -> int:
    """Prints `{"resolved": [...], "unresolved": [...]}`. A ref that can't
    resolve to a live ImageStreamTag (no BuildConfig ever produced one -
    e.g. rag-ingestion's images.compiler, a documented pre-existing gap
    unrelated to signing, same one check_no_latest_tags.py's own docstring
    already calls out) is reported separately, not treated as a script
    failure - there is nothing to sign or verify for an image that was
    never built. Always exits 0: this is a listing operation, not the
    verification itself - the caller (ansible/tasks/
    verify_image_signatures.yml) decides what to do with each list."""
    refs = _collect_first_party_refs()
    resolved = []
    unresolved = []
    for ref in refs:
        try:
            resolved.append(_resolve_ref_dict(ref))
        except RuntimeError as exc:
            unresolved.append({"image": ref.image, "error": str(exc)})

    print(json.dumps({"resolved": resolved, "unresolved": unresolved}, indent=2))
    return 0


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
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--list-refs",
        action="store_true",
        help="print scanned/resolved refs as JSON instead of verifying them (no cosign needed)",
    )
    args = parser.parse_args()

    if args.list_refs:
        return list_refs()

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
