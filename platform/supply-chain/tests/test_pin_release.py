"""ADR-0115 regression tests for pin_release.py. Unlike its sibling
policy-as-code checks (check_no_latest_tags.py, check_build_matrix.py -
read-only, no test suite of their own in this repository's convention),
pin_release.py mutates chart files, so its line-matching invariants
(file order == walk order; each file's Nth literal `tag:` line ==
manifest pin for the Nth `tag`-valued finding in that file) get a real
test rather than only the one-off manual verification that produced this
file.

Runs entirely against a throwaway copy of the real gitops/charts/*/
values.yaml files under a temp directory - never touches the actual
repository state.

Run from this directory:

    python3 tests/test_pin_release.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SUPPLY_CHAIN_DIR = TESTS_DIR.parent
REPO_ROOT = SUPPLY_CHAIN_DIR.parents[1]

sys.path.insert(0, str(SUPPLY_CHAIN_DIR))
import pin_release  # noqa: E402

FULL_PINS = [
    {"chart_values": "gitops/charts/agent-runtime/values.yaml", "path": "image.tag", "tag": "v0.1.0"},
    {"chart_values": "gitops/charts/ai-gateway/values.yaml", "path": "image.tag", "tag": "v0.1.0"},
    {"chart_values": "gitops/charts/mcp-gateway/values.yaml", "path": "image.tag", "tag": "v0.1.0"},
    {"chart_values": "gitops/charts/mcp-sales-db/values.yaml", "path": "image.tag", "tag": "v0.1.0"},
    {"chart_values": "gitops/charts/rag-service/values.yaml", "path": "image.tag", "tag": "v0.1.0"},
    {"chart_values": "gitops/charts/tekos/values.yaml", "path": "image.tag", "tag": "v0.1.0"},
    {"chart_values": "gitops/charts/rag-ingestion/values.yaml", "path": "images.ingestion.tag", "tag": "v0.1.0"},
    {"chart_values": "gitops/charts/rag-ingestion/values.yaml", "path": "images.compiler.tag", "tag": "v0.1.0"},
]


def _repoint_module_at(tmp_root: Path):
    """Repoints the single imported pin_release module's REPO_ROOT/
    LEDGER_PATH constants at an isolated temp tree for one test. Every
    test calls this first, so no state leaks between tests despite the
    module being imported once at module load time (re-importing a
    dataclass-bearing module under a synthetic name breaks on Python 3.9 -
    `_get_field` looks the module up in `sys.modules` by `__module__`
    before postponed-annotation evaluation can resolve, which a spec-based
    "shadow" import never registers there)."""
    pin_release.REPO_ROOT = tmp_root
    pin_release.LEDGER_PATH = tmp_root / "platform" / "supply-chain" / "pinned-releases.yaml"
    return pin_release


def _build_scratch_tree(tmp_root: Path) -> None:
    charts_src = REPO_ROOT / "gitops" / "charts"
    for chart_dir in charts_src.iterdir():
        values = chart_dir / "values.yaml"
        if values.is_file():
            dest = tmp_root / "gitops" / "charts" / chart_dir.name
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(values, dest / "values.yaml")
    (tmp_root / "platform" / "supply-chain").mkdir(parents=True, exist_ok=True)


def _run(module, manifest: dict, dry_run: bool = False) -> int:
    import argparse
    import yaml

    manifest_path = module.REPO_ROOT / "manifest.yaml"
    manifest_path.write_text(yaml.dump(manifest))
    args = argparse.Namespace(manifest=manifest_path, dry_run=dry_run)
    sys.argv = ["pin_release.py", "--manifest", str(manifest_path)] + (["--dry-run"] if dry_run else [])
    return module.main()


def test_full_manifest_pins_everything_and_preserves_comments() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        _build_scratch_tree(tmp_root)
        module = _repoint_module_at(tmp_root)

        before = (tmp_root / "gitops/charts/tekos/values.yaml").read_text()
        rc = _run(module, {"release_tag": "v0.1.0", "pins": FULL_PINS})
        assert rc == 0, "expected pin_release.py to succeed on a complete, correct manifest"

        after = (tmp_root / "gitops/charts/tekos/values.yaml").read_text()
        assert "tag: latest" not in after
        assert "tag: v0.1.0" in after
        # Every line except the tag line itself must be byte-identical -
        # comments and structure survive a text-level edit.
        before_lines = before.splitlines()
        after_lines = after.splitlines()
        assert len(before_lines) == len(after_lines)
        changed = [i for i in range(len(before_lines)) if before_lines[i] != after_lines[i]]
        assert changed == [14], f"expected only the tag line (index 14) to change, got {changed}"

        remaining = module._current_findings()
        assert remaining == [], f"expected no non-immutable tags left, found {remaining}"

        ledger_path = tmp_root / "platform/supply-chain/pinned-releases.yaml"
        assert ledger_path.exists(), "expected the audit ledger to be written"
        assert "v0.1.0" in ledger_path.read_text()


def test_dry_run_writes_nothing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        _build_scratch_tree(tmp_root)
        module = _repoint_module_at(tmp_root)

        before = (tmp_root / "gitops/charts/agent-runtime/values.yaml").read_text()
        rc = _run(module, {"release_tag": "v0.1.0", "pins": FULL_PINS}, dry_run=True)
        assert rc == 0

        after = (tmp_root / "gitops/charts/agent-runtime/values.yaml").read_text()
        assert before == after, "dry-run must not modify any file"
        ledger_path = tmp_root / "platform/supply-chain/pinned-releases.yaml"
        assert not ledger_path.exists(), "dry-run must not write the ledger"


def test_incomplete_manifest_is_rejected_and_changes_nothing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        _build_scratch_tree(tmp_root)
        module = _repoint_module_at(tmp_root)

        before = (tmp_root / "gitops/charts/agent-runtime/values.yaml").read_text()
        partial = [p for p in FULL_PINS if p["chart_values"] != "gitops/charts/tekos/values.yaml"]
        rc = _run(module, {"release_tag": "v0.1.0", "pins": partial})
        assert rc == 1, "expected failure when the manifest omits a currently non-immutable field"

        after = (tmp_root / "gitops/charts/agent-runtime/values.yaml").read_text()
        assert before == after, "a rejected manifest must not partially apply"
        tekos_after = (tmp_root / "gitops/charts/tekos/values.yaml").read_text()
        assert "tag: latest" in tekos_after


def test_manifest_with_unknown_path_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        _build_scratch_tree(tmp_root)
        module = _repoint_module_at(tmp_root)

        bad_pins = FULL_PINS + [
            {"chart_values": "gitops/charts/keycloak/values.yaml", "path": "image.tag", "tag": "v0.1.0"}
        ]
        rc = _run(module, {"release_tag": "v0.1.0", "pins": bad_pins})
        assert rc == 1, "expected failure when the manifest names a field that isn't currently non-immutable"


def test_rerunning_a_stale_manifest_after_success_is_rejected() -> None:
    """Once fields are pinned, the same manifest that just worked becomes
    invalid (every one of its paths is now 'extra', since none of them are
    non-immutable anymore) - locks in that pin_release.py never silently
    re-applies or no-ops on a second run with stale input."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        _build_scratch_tree(tmp_root)
        module = _repoint_module_at(tmp_root)

        manifest = {"release_tag": "v0.1.0", "pins": FULL_PINS}
        assert _run(module, manifest) == 0
        assert _run(module, manifest) == 1, "a manifest with no remaining non-immutable targets must fail"


TESTS = [
    test_full_manifest_pins_everything_and_preserves_comments,
    test_dry_run_writes_nothing,
    test_incomplete_manifest_is_rejected_and_changes_nothing,
    test_manifest_with_unknown_path_is_rejected,
    test_rerunning_a_stale_manifest_after_success_is_rejected,
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
