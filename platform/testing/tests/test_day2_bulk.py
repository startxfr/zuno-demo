"""ADR-0058 acceptance tests for the deterministic, cluster-free parts of
platform/testing/day2_bulk.py: percentile math and scenario-corpus
extraction. The actual HTTP replay (run()'s main loop) needs a live BFF,
same "no live cluster" constraint as every evaluations/*.py script - not
covered here, same convention as
platform/supply-chain/tests/test_pin_release.py.

Run from this directory:

    python3 tests/test_day2_bulk.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TESTING_DIR = TESTS_DIR.parent

sys.path.insert(0, str(TESTING_DIR))
import day2_bulk  # noqa: E402


def test_percentile_of_empty_list_is_zero() -> None:
    assert day2_bulk._percentile([], 0.50) == 0.0


def test_percentile_p50_and_p95_of_sorted_values() -> None:
    values = [float(v) for v in range(1, 101)]  # 1..100, already sorted
    assert day2_bulk._percentile(values, 0.50) == 51.0
    assert day2_bulk._percentile(values, 0.95) == 96.0


def test_percentile_max_is_last_element() -> None:
    values = [10.0, 20.0, 30.0]
    assert day2_bulk._percentile(values, 1.0) == 30.0


def test_scenario_prompts_extracts_only_message_bearing_entries() -> None:
    tmpdir = Path(tempfile.mkdtemp())
    original_script_dir = day2_bulk.SCRIPT_DIR
    try:
        agent_dir = tmpdir / "demo-agent"
        agent_dir.mkdir()
        (agent_dir / "scenarios.yaml").write_text(
            "scenarios:\n"
            "  - id: 1\n"
            "    title: no message here\n"
            "    type: portal_lists_all_agents\n"
            "  - id: 2\n"
            "    title: has a message\n"
            "    type: chat_basic_qa\n"
            '    message: "Hello there"\n'
        )
        day2_bulk.SCRIPT_DIR = tmpdir
        day2_bulk.AGENT = "demo-agent"
        prompts = day2_bulk._scenario_prompts()
        assert prompts == ["Hello there"]
    finally:
        day2_bulk.SCRIPT_DIR = original_script_dir
        day2_bulk.AGENT = "tekos"
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_scenario_prompts_returns_empty_list_when_file_missing() -> None:
    tmpdir = Path(tempfile.mkdtemp())
    original_script_dir = day2_bulk.SCRIPT_DIR
    try:
        day2_bulk.SCRIPT_DIR = tmpdir
        day2_bulk.AGENT = "no-such-agent"
        assert day2_bulk._scenario_prompts() == []
    finally:
        day2_bulk.SCRIPT_DIR = original_script_dir
        day2_bulk.AGENT = "tekos"
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_run_returns_empty_when_bulk_interactions_not_set() -> None:
    original = day2_bulk.BULK_INTERACTIONS
    try:
        day2_bulk.BULK_INTERACTIONS = 0
        assert day2_bulk.run() == []
    finally:
        day2_bulk.BULK_INTERACTIONS = original


TESTS = [
    test_percentile_of_empty_list_is_zero,
    test_percentile_p50_and_p95_of_sorted_values,
    test_percentile_max_is_last_element,
    test_scenario_prompts_extracts_only_message_bearing_entries,
    test_scenario_prompts_returns_empty_list_when_file_missing,
    test_run_returns_empty_when_bulk_interactions_not_set,
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
