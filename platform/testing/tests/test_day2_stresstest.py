"""WP-156 tests for platform/testing/day2_stresstest.py's cluster-free
decisions: the stress_test layer is reported, never run, and the UnifAI
sessions every layer opened are cleaned up once. run_scenarios is replaced
by a stub module; no network.

Run from this directory:

    python3 tests/test_day2_stresstest.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import types
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TESTING_DIR = TESTS_DIR.parent

sys.path.insert(0, str(TESTING_DIR))
import day2_stresstest  # noqa: E402


def _stub_run_scenarios(unifai=None):
    mod = types.ModuleType("run_scenarios")
    mod.TARGET = "unifai"
    mod._unifai_target = unifai
    return mod


def test_stress_test_layer_is_reported_not_run() -> None:
    tmpdir = Path(tempfile.mkdtemp())
    saved = (day2_stresstest.SCRIPT_DIR, day2_stresstest.AGENT)
    try:
        (tmpdir / "tekos").mkdir()
        # A stale module left in a mounted ConfigMap: would raise if it were loaded.
        (tmpdir / "tekos" / "stress_test.py").write_text("raise RuntimeError('must not be loaded')\n")
        day2_stresstest.SCRIPT_DIR = tmpdir
        day2_stresstest.AGENT = "tekos"
        rows = day2_stresstest._stress_test_results()
        assert len(rows) == 1 and rows[0].category == "coverage" and "NOT RUN" in rows[0].detail
        assert rows[0].passed
    finally:
        day2_stresstest.SCRIPT_DIR, day2_stresstest.AGENT = saved
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_a_skipped_security_check_is_not_run_never_a_failure_nor_a_security_pass() -> None:
    """A check that cannot apply (the Tekos -> Arkos delegation checks while the release declares
    nothing) must not turn the run red, and must not be counted among the security passes."""
    from dataclasses import dataclass

    @dataclass
    class R:
        name: str
        passed: bool
        detail: str = ""
        skipped: bool = False

    module = types.ModuleType("security_checks")
    module.run = lambda: [
        R("real_check", True, "ok"),
        R("failing_check", False, "status=500"),
        R("delegation_x", False, "skipped: delegation is not enabled", skipped=True),
    ]
    saved = day2_stresstest._load_security_checks
    day2_stresstest._load_security_checks = lambda: module
    try:
        rows = {r.id: r for r in day2_stresstest._security_results()}
    finally:
        day2_stresstest._load_security_checks = saved
    assert (rows["real_check"].category, rows["real_check"].passed) == ("security", True)
    assert (rows["failing_check"].category, rows["failing_check"].passed) == ("security", False)
    skipped = rows["delegation_x"]
    assert (skipped.category, skipped.passed) == ("coverage", True), skipped
    assert skipped.detail.startswith("NOT RUN: skipped: delegation is not enabled"), skipped.detail


def test_rag_ingestion_layer_is_gone() -> None:
    assert not hasattr(day2_stresstest, "_rag_ingestion_results")
    assert not hasattr(day2_stresstest, "_load_stress_test")


def _run_main_capturing_stderr() -> str:
    captured = []
    real_stderr = sys.stderr
    sys.stderr = types.SimpleNamespace(write=captured.append, flush=lambda: None)
    try:
        assert day2_stresstest.main() == 0
    finally:
        sys.stderr = real_stderr
    return "".join(captured)


def test_main_cleans_up_unifai_sessions() -> None:
    class FakeTarget:
        def cleanup(self):
            return (3, 1)

    saved_mod = sys.modules.get("run_scenarios")
    saved_run = day2_stresstest._safe_run
    try:
        day2_stresstest._safe_run = lambda layer, fn: []
        sys.modules["run_scenarios"] = _stub_run_scenarios(FakeTarget())
        assert "cleanup: 3 conversation(s) removed, 1 failed" in _run_main_capturing_stderr()
        # No UnifAI session was ever opened: nothing to clean up, no target created for it.
        sys.modules["run_scenarios"] = _stub_run_scenarios(None)
        assert "cleanup: 0 conversation(s) removed, 0 failed" in _run_main_capturing_stderr()
    finally:
        day2_stresstest._safe_run = saved_run
        if saved_mod is None:
            sys.modules.pop("run_scenarios", None)
        else:
            sys.modules["run_scenarios"] = saved_mod


TESTS = [
    test_stress_test_layer_is_reported_not_run,
    test_a_skipped_security_check_is_not_run_never_a_failure_nor_a_security_pass,
    test_rag_ingestion_layer_is_gone,
    test_main_cleans_up_unifai_sessions,
]


def main() -> int:
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
