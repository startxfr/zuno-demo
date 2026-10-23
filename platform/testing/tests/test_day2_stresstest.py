"""WP-156 tests for platform/testing/day2_stresstest.py's cluster-free
decisions: which layers run under the UnifAI target, and which cleanup
mechanism each created conversation goes through. run_scenarios is replaced
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


def _stub_run_scenarios(target: str, unifai=None, run_ids=()):
    mod = types.ModuleType("run_scenarios")
    mod.TARGET = target
    mod._unifai_target = unifai
    mod._CREATED_RUN_IDS = list(run_ids)
    mod.cleanup_created_runs = lambda: (len(mod._CREATED_RUN_IDS), 0)
    return mod


def test_stress_test_module_is_reported_not_run_under_unifai() -> None:
    tmpdir = Path(tempfile.mkdtemp())
    saved = (day2_stresstest.SCRIPT_DIR, day2_stresstest.AGENT, sys.modules.get("run_scenarios"))
    try:
        (tmpdir / "tekos").mkdir()
        # Would raise if it were loaded: proves it is not run.
        (tmpdir / "tekos" / "stress_test.py").write_text("raise RuntimeError('must not be loaded')\n")
        day2_stresstest.SCRIPT_DIR = tmpdir
        day2_stresstest.AGENT = "tekos"
        sys.modules["run_scenarios"] = _stub_run_scenarios("unifai")
        rows = day2_stresstest._stress_test_results()
        assert len(rows) == 1 and rows[0].category == "coverage" and "NOT RUN" in rows[0].detail
    finally:
        day2_stresstest.SCRIPT_DIR, day2_stresstest.AGENT = saved[0], saved[1]
        if saved[2] is None:
            sys.modules.pop("run_scenarios", None)
        else:
            sys.modules["run_scenarios"] = saved[2]
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_rag_ingestion_layer_is_gone() -> None:
    assert not hasattr(day2_stresstest, "_rag_ingestion_results")


def test_main_cleans_up_unifai_sessions_and_leftover_run_ids() -> None:
    class FakeTarget:
        def cleanup(self):
            return (3, 1)

    saved_mod = sys.modules.get("run_scenarios")
    saved_run = day2_stresstest._safe_run
    try:
        sys.modules["run_scenarios"] = _stub_run_scenarios("unifai", FakeTarget(), run_ids=[("p", "r1")])
        day2_stresstest._safe_run = lambda layer, fn: []
        captured = []
        real_stderr = sys.stderr
        sys.stderr = types.SimpleNamespace(write=captured.append, flush=lambda: None)
        try:
            assert day2_stresstest.main() == 0
        finally:
            sys.stderr = real_stderr
        assert "cleanup: 4 conversation(s) removed, 1 failed" in "".join(captured)
    finally:
        day2_stresstest._safe_run = saved_run
        if saved_mod is None:
            sys.modules.pop("run_scenarios", None)
        else:
            sys.modules["run_scenarios"] = saved_mod


TESTS = [
    test_stress_test_module_is_reported_not_run_under_unifai,
    test_rag_ingestion_layer_is_gone,
    test_main_cleans_up_unifai_sessions_and_leftover_run_ids,
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
