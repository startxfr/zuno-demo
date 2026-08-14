"""ADR-0106 tests for sign_okf_bundle.py's digest computation - the part
that needs no cosign binary or real signing credentials, and the actual
mechanism that makes a tampered bundle detectable (a changed digest is
what `cosign verify-blob` would refuse to match against a prior
signature; `components/agent-runtime/tests/test_bundle_signing.py` covers
the AgentRegistry-side wrapping of that refusal).

Run from this directory:

    python3 tests/test_sign_okf_bundle.py
"""
from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile

SUPPLY_CHAIN_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUPPLY_CHAIN_DIR))

import sign_okf_bundle  # noqa: E402


def _make_bundle(tmp: pathlib.Path, files: dict) -> pathlib.Path:
    bundle_dir = tmp / "agents" / "demo"
    for rel, content in files.items():
        path = bundle_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return bundle_dir


def test_digest_is_deterministic_across_runs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        bundle_dir = _make_bundle(
            pathlib.Path(tmp), {"agent.okf.md": "---\nname: demo\n---\nbody", "tasks/t.md": "task"}
        )
        first = sign_okf_bundle.compute_digest(bundle_dir)
        second = sign_okf_bundle.compute_digest(bundle_dir)
        assert first == second


def test_digest_changes_when_content_changes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        bundle_dir = _make_bundle(
            pathlib.Path(tmp), {"agent.okf.md": "---\nname: demo\n---\nbody", "tasks/t.md": "task"}
        )
        before = sign_okf_bundle.compute_digest(bundle_dir)

        (bundle_dir / "tasks" / "t.md").write_text("TAMPERED task content")
        after = sign_okf_bundle.compute_digest(bundle_dir)

        assert before != after, "a content change must change the digest (this is what makes tampering detectable)"


def test_digest_changes_when_a_file_is_added_or_removed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        bundle_dir = _make_bundle(pathlib.Path(tmp), {"agent.okf.md": "---\nname: demo\n---\nbody"})
        before = sign_okf_bundle.compute_digest(bundle_dir)

        (bundle_dir / "tasks" / "new.md").parent.mkdir(parents=True, exist_ok=True)
        (bundle_dir / "tasks" / "new.md").write_text("a new task, not present when signed")
        after_add = sign_okf_bundle.compute_digest(bundle_dir)
        assert after_add != before

        (bundle_dir / "tasks" / "new.md").unlink()
        after_remove = sign_okf_bundle.compute_digest(bundle_dir)
        assert after_remove == before, "removing the added file must restore the original digest"


def test_digest_is_independent_of_filesystem_iteration_order() -> None:
    """Files are hashed in sorted order regardless of creation order -
    proves the digest a signer computes doesn't depend on incidental
    filesystem/OS behavior."""
    with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
        bundle_a = _make_bundle(pathlib.Path(tmp1), {"b.md": "B", "a.md": "A", "c/d.md": "D"})
        bundle_b = _make_bundle(pathlib.Path(tmp2), {"a.md": "A", "c/d.md": "D", "b.md": "B"})
        assert sign_okf_bundle.compute_digest(bundle_a) == sign_okf_bundle.compute_digest(bundle_b)


def test_digest_of_missing_or_empty_bundle_raises() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        missing = pathlib.Path(tmp) / "does-not-exist"
        try:
            sign_okf_bundle.compute_digest(missing)
            raise AssertionError("expected BundleError for a missing directory")
        except sign_okf_bundle.BundleError:
            pass

        empty_dir = pathlib.Path(tmp) / "empty"
        empty_dir.mkdir()
        try:
            sign_okf_bundle.compute_digest(empty_dir)
            raise AssertionError("expected BundleError for an empty directory")
        except sign_okf_bundle.BundleError:
            pass


TESTS = [
    test_digest_is_deterministic_across_runs,
    test_digest_changes_when_content_changes,
    test_digest_changes_when_a_file_is_added_or_removed,
    test_digest_is_independent_of_filesystem_iteration_order,
    test_digest_of_missing_or_empty_bundle_raises,
]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
