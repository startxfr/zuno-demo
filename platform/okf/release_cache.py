#!/usr/bin/env python3
"""The admitted agents release on a workstation or a CI runner (ADR-0580, WP-165).

Agent definitions and the corp policies live in startxfr/zuno-demo-agents
(ADR-0576); this tree pins one release in platform/okf/agents.lock. Every
repository-side reader of that content (check_docs.py, the knowledge and
quota checks, evaluations/, the Ansible checks and the Job ConfigMaps) gets
it from here instead of a copy in git:

    release_dir()   the extracted release of the lock, as a directory holding
                    agents/<name>/..., policies/... and okf-index.json

Resolution order:

1. ZUNO_OKF_RELEASE_DIR, when set: a directory already extracted (and
   verified) by the caller, used as is. Containers and CI steps that ran
   the extraction themselves pass it.
2. .cache/okf-release/<digest>/ in this checkout (gitignored), extracted once
   per locked digest by admit_okf_bundle.extract, which verifies the keyless
   signatures and attestations offline before writing anything. A directory
   is only used once its `.verified` marker exists, written last.

`.cache/okf-release/current` is a symlink to the locked digest's directory,
refreshed on every call, for readers that cannot compute a path (the
kustomize configMapGenerators under ansible/roles/*/kustomize/).

Needs cosign (v2) and oras on PATH the first time a digest is extracted,
like admission. Run from the repository root:

    python3 platform/okf/release_cache.py          # extract if needed, print the path
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile
from typing import Optional

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE_ROOT = REPO_ROOT / ".cache" / "okf-release"
CURRENT_LINK = CACHE_ROOT / "current"
ENV_VAR = "ZUNO_OKF_RELEASE_DIR"
MARKER = ".verified"

sys.path.insert(0, str(REPO_ROOT / "platform" / "supply-chain"))

import admit_okf_bundle as admit  # noqa: E402


class ReleaseUnavailable(RuntimeError):
    pass


def _digest(reference: str) -> str:
    return reference.rsplit("@sha256:", 1)[1]


def _refresh_current(target: pathlib.Path) -> None:
    """Point `current` at the locked digest's directory (relative link)."""
    try:
        if CURRENT_LINK.is_symlink() and os.readlink(CURRENT_LINK) == target.name:
            return
        tmp = CACHE_ROOT / f".current-{os.getpid()}"
        if tmp.is_symlink() or tmp.exists():
            tmp.unlink()
        tmp.symlink_to(target.name)
        os.replace(tmp, CURRENT_LINK)
    except OSError:
        # The link only serves the kustomize readers; the path is returned anyway.
        pass


def release_dir(reference: Optional[str] = None) -> pathlib.Path:
    """The extracted release of `reference` (default: the lock)."""
    override = os.environ.get(ENV_VAR)
    if override and reference is None:
        path = pathlib.Path(override)
        if not (path / "okf-index.json").is_file():
            raise ReleaseUnavailable(f"{ENV_VAR}={override} holds no extracted release (no okf-index.json)")
        return path
    reference = reference or admit.read_lock()
    if not reference or "@sha256:" not in reference:
        raise ReleaseUnavailable("platform/okf/agents.lock pins no release")
    target = CACHE_ROOT / _digest(reference)
    if not (target / MARKER).is_file():
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        staging = pathlib.Path(tempfile.mkdtemp(prefix=".extract-", dir=CACHE_ROOT))
        try:
            admit.extract(reference, staging)
            (staging / MARKER).write_text(reference + "\n", encoding="utf-8")
            staging.chmod(0o755)  # mkdtemp's 0700 would hide it from other users
            if target.exists():
                shutil.rmtree(target)
            os.replace(staging, target)
        except admit.AdmissionError as exc:
            raise ReleaseUnavailable(f"cannot extract {reference}: {exc}") from exc
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
    _refresh_current(target)
    return target


def main() -> int:
    try:
        print(release_dir())
    except ReleaseUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0



CONFORMANCE_ENV_VAR = "ZUNO_OKF_CONFORMANCE_DIR"


def conformance_dir() -> Optional[pathlib.Path]:
    """The OKF conformance cases (ADR-0508), or None when none are available.

    ZUNO_OKF_CONFORMANCE_DIR first (the `cases/` directory, e.g. a checkout of
    zuno-demo-agents/conformance/cases), then `conformance/cases/` inside the
    admitted release once a release carries it. Readers' fixture tests skip
    loudly on None rather than pass on nothing.
    """
    override = os.environ.get(CONFORMANCE_ENV_VAR)
    if override:
        path = pathlib.Path(override)
        if not path.is_dir():
            raise ReleaseUnavailable(f"{CONFORMANCE_ENV_VAR}={override} is not a directory")
        return path
    try:
        candidate = release_dir() / "conformance" / "cases"
    except ReleaseUnavailable:
        return None
    return candidate if candidate.is_dir() else None

def read_index(release: pathlib.Path) -> dict:
    """okf-index.json of an extracted release (the corp artifact's index layer),
    refused by name when absent or of an unknown schemaVersion (ADR-0508)."""
    import json

    path = release / "okf-index.json"
    if not path.is_file():
        raise ReleaseUnavailable(f"{path}: the release holds no okf-index.json")
    index = json.loads(path.read_text(encoding="utf-8"))
    if index.get("schemaVersion") != 1:
        raise ReleaseUnavailable(f"{path}: unsupported index schemaVersion {index.get('schemaVersion')!r} (supported: 1)")
    return index

if __name__ == "__main__":
    sys.exit(main())
