#!/usr/bin/env python3
"""ADR-0115 policy-as-code check, stage 1 of WP-04 (docs/roadmap/
work-packages/wp-04-supply-chain-completion.md): "signature verification
is exercised as part of trusted promotion/deployment." Walks every
`gitops/charts/*/values.yaml` for first-party image references (anything
published under `REGISTRY`/`REGISTRY_NAMESPACE`, i.e. built and signed by
`.github/workflows/build-publish.yml`) and runs `cosign verify` against
each one that already carries an immutable tag, checking the image was
signed by that exact workflow's keyless GitHub OIDC identity - not merely
signed by *someone*.

Deliberately scopes to immutable-tagged references only: a `tag: latest`
entry (ADR-0115 gap 2, tracked by check_no_latest_tags.py) has no
meaningful digest to verify signatures against, and gap 7 (no real
build-publish-sign cycle has ever run) means every first-party chart is
on `latest` as of this check's introduction - so this genuinely finds
nothing to verify yet and passes trivially. That is the honest, correct
state until a real release exists (RELEASING.md), not a loosened check:
once `pin_release.py` (stage 3) replaces a `latest` tag with a real
immutable one, this check starts actually verifying it.

No live cluster needed, but DOES need network access to the registry and
a `cosign` binary on PATH once there is something to verify - exactly the
gap-7 dependency ADR-0115's Implementation state describes. Wired into
`.github/workflows/lint.yml` with `continue-on-error: true` until stage 3
lands real signed images (mirrors check_no_latest_tags.py's own
convention exactly, and for the same reason: this becomes a hard, useful
gate only once the artifacts it inspects are real).

Run from the repository root:

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
BUILD_PUBLISH_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "build-publish.yml"

# Matches build-publish.yml's own `env:` block (REGISTRY, REGISTRY_NAMESPACE)
# and RELEASING.md's documented `quay.io/zuno-demo/<component>` naming -
# only images published under this prefix were built/signed by our own
# workflow, so only these get verified here. Third-party images
# (postgresql, keycloak, redis, ...) are out of scope for this check.
FIRST_PARTY_REGISTRY_PREFIX = "quay.io/zuno-demo/"

# The exact keyless-signing identity build-publish.yml signs with: GitHub's
# OIDC token for a run of that workflow file, on this repository
# (ADR-0004: startxfr/zuno-demo is the canonical source repository).
EXPECTED_OIDC_ISSUER = "https://token.actions.githubusercontent.com"
EXPECTED_IDENTITY_REGEXP = (
    r"^https://github\.com/startxfr/zuno-demo/\.github/workflows/build-publish\.yml@refs/"
)

IGNORED_TAG_VALUES = {"latest", ""}


@dataclass
class ImageRef:
    file: str
    path: str
    image: str  # "quay.io/zuno-demo/<name>:<tag>"


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


def _verify_one(cosign_bin: str, image: str) -> Optional[str]:
    """Returns None on success, an error message on failure. Never raises -
    a registry/network problem is reported as a finding, not a crash,
    matching this file's own `continue-on-error` posture in CI."""
    try:
        result = subprocess.run(
            [
                cosign_bin,
                "verify",
                "--certificate-oidc-issuer",
                EXPECTED_OIDC_ISSUER,
                "--certificate-identity-regexp",
                EXPECTED_IDENTITY_REGEXP,
                image,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return f"cosign verify timed out for {image}"
    except OSError as exc:
        return f"failed to run cosign for {image}: {exc}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "no output").strip().splitlines()[-1:]
        return f"signature verification failed for {image}: {'; '.join(detail) or 'unknown error'}"
    return None


def main() -> int:
    refs = _collect_first_party_refs()

    print(
        f"Scanned gitops/charts/*/values.yaml for first-party image references "
        f"under {FIRST_PARTY_REGISTRY_PREFIX} with an immutable tag."
    )
    if not refs:
        print(
            "\nRESULT: PASS - no immutable-tagged first-party image reference found yet "
            "(every chart is still on `tag: latest` pending ADR-0115 gap 7 - a real "
            "build-publish-sign cycle; see RELEASING.md). Nothing to verify."
        )
        return 0

    cosign_bin = _cosign_path()
    if cosign_bin is None:
        print(
            f"\n{len(refs)} immutable-tagged image reference(s) found, but no `cosign` "
            "binary is on PATH to verify them with:"
        )
        for ref in refs:
            print(f"  ? {ref.file}: {ref.path} = {ref.image!r}")
        print(
            "\nRESULT: FAIL - install cosign (`.github/workflows/build-publish.yml` uses "
            "sigstore/cosign-installer) to actually verify these signatures."
        )
        return 1

    findings: List[Finding] = []
    for ref in refs:
        print(f"Verifying {ref.image} (from {ref.file}: {ref.path}) ...")
        error = _verify_one(cosign_bin, ref.image)
        if error:
            findings.append(Finding(error))

    if not findings:
        print(f"\nRESULT: PASS - all {len(refs)} immutable-tagged first-party image(s) verified.")
        return 0

    print(f"\n{len(findings)} signature verification failure(s):")
    for f in findings:
        print(f"  ✗ {f.message}")
    print(
        "\nRESULT: FAIL - an immutable-tagged first-party image did not verify against "
        f"the expected build-publish.yml keyless identity ({EXPECTED_IDENTITY_REGEXP})."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
