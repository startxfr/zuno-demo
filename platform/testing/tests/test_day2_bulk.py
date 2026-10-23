"""ADR-0058 acceptance tests for the deterministic, cluster-free parts of
platform/testing/day2_bulk.py: percentile math and scenario-corpus
extraction, and (WP-156) the replay loop driven through a fake UnifAI
target - the real transport needs a live UnifAI, same "no live cluster"
constraint as every evaluations/*.py script.

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


class _Run:
    def __init__(self, status, reply="", raw=None):
        self.status, self.reply, self.raw = status, reply, raw or {}


class _FakeTarget:
    """Stands in for evaluations/common/unifai_target.UnifaiTarget."""

    def __init__(self, runs):
        self._runs = list(runs)
        self.created = 0
        self.cleaned = False

    def workflow_id(self, persona):
        return "bp-1"

    def create(self, persona, blueprint_id):
        assert blueprint_id == "bp-1"
        self.created += 1
        return f"s-{self.created}"

    def run(self, persona, message, session_id=None, timeout=60):
        assert session_id == f"s-{self.created}"  # each call runs in the session created for it
        return self._runs.pop(0)

    def cleanup(self):
        self.cleaned = True
        return (self.created, 0)


def _with_fake(runs, bulk):
    saved = (day2_bulk._TARGET, day2_bulk.BULK_INTERACTIONS, day2_bulk.ZUNO_AGENT_STATUS, day2_bulk._scenario_prompts)
    fake = _FakeTarget(runs)
    day2_bulk._TARGET = fake
    day2_bulk.BULK_INTERACTIONS = bulk
    day2_bulk.ZUNO_AGENT_STATUS = "active"
    day2_bulk._scenario_prompts = lambda: ["hello"]
    try:
        return day2_bulk.run(), fake
    finally:
        day2_bulk._TARGET, day2_bulk.BULK_INTERACTIONS, day2_bulk.ZUNO_AGENT_STATUS, day2_bulk._scenario_prompts = saved


def test_run_drives_unifai_turns_and_summarises() -> None:
    results, fake = _with_fake([_Run(200, "a"), _Run(200, ""), _Run(599, raw={"error": "The read operation timed out"}), _Run(200, "b")], 3)
    assert len(results) == 1 and results[0].category == "bulk_load"
    # call 2 has an empty reply (error), call 3 times out once and is retried successfully
    assert "count=3 errors=1 (timeouts=0)" in results[0].detail and not results[0].passed
    assert fake.created == 4


def test_run_skips_placeholders_without_touching_unifai() -> None:
    saved = (day2_bulk._TARGET, day2_bulk.BULK_INTERACTIONS, day2_bulk.ZUNO_AGENT_STATUS)
    try:
        day2_bulk._TARGET = None
        day2_bulk.BULK_INTERACTIONS = 5
        day2_bulk.ZUNO_AGENT_STATUS = "placeholder"
        results = day2_bulk.run()
        assert len(results) == 1 and results[0].category == "coverage" and day2_bulk._TARGET is None
    finally:
        day2_bulk._TARGET, day2_bulk.BULK_INTERACTIONS, day2_bulk.ZUNO_AGENT_STATUS = saved


def test_cleanup_without_a_target_is_a_no_op() -> None:
    saved = day2_bulk._TARGET
    try:
        day2_bulk._TARGET = None
        assert day2_bulk._cleanup_created_runs() == (0, 0)
    finally:
        day2_bulk._TARGET = saved


TESTS = [
    test_percentile_of_empty_list_is_zero,
    test_percentile_p50_and_p95_of_sorted_values,
    test_percentile_max_is_last_element,
    test_scenario_prompts_extracts_only_message_bearing_entries,
    test_scenario_prompts_returns_empty_list_when_file_missing,
    test_run_returns_empty_when_bulk_interactions_not_set,
    test_run_drives_unifai_turns_and_summarises,
    test_run_skips_placeholders_without_touching_unifai,
    test_cleanup_without_a_target_is_a_no_op,
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
