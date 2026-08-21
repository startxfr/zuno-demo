#!/usr/bin/env python3
"""ADR-0504 tasks/ suite: per-task assertions for Finage - live_read_tool
within allowed_tools, primary_task declared in zuno.tasks, project_required
(ADR-0512) tasks well-formed. Static repository checks only.

Run directly (from anywhere) or via
platform/okf/run_agent_contract_tests.py:

    python3 agents/finage/tests/tasks/test_task_declarations.py
"""
from __future__ import annotations

import pathlib
import sys

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
AGENT_DIR = REPO_ROOT / "agents" / "finage"


def _split_frontmatter(path: pathlib.Path) -> dict:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    assert len(parts) >= 3, f"{path}: expected a leading '---' YAML frontmatter block"
    return yaml.safe_load(parts[1]) or {}


def _agent_zuno() -> dict:
    return _split_frontmatter(AGENT_DIR / "agent.okf.md")["zuno"]


def _task_zuno(task_name: str) -> dict:
    return _split_frontmatter(AGENT_DIR / "tasks" / f"{task_name}.md").get("zuno") or {}


def test_primary_task_is_declared_in_zuno_tasks() -> None:
    agent = _agent_zuno()
    assert agent["primary_task"] in agent["tasks"], (
        f"primary_task {agent['primary_task']!r} is not one of the declared zuno.tasks {agent['tasks']}"
    )


def test_every_declared_task_has_a_task_file() -> None:
    agent = _agent_zuno()
    for task_name in agent["tasks"]:
        task_path = AGENT_DIR / "tasks" / f"{task_name}.md"
        assert task_path.is_file(), f"zuno.tasks lists {task_name!r} but {task_path} does not exist"


def test_live_read_tool_is_within_its_own_allowed_tools() -> None:
    """ADR-0342/WP-33: a task's live_read_tool (the allowed_tools entry a
    conditional live-read branch would invoke) must be a tool that task
    actually declares. Finage's tasks don't set live_read_tool today
    (answer-finance-question's own body prose explains why: every sxa.*
    capability needs structured numeric arguments, not a free-text query,
    so it doesn't fit tool_call_node's generic calling convention); this
    assertion still holds vacuously and guards against a future task
    declaring one incorrectly."""
    agent = _agent_zuno()
    checked = 0
    for task_name in agent["tasks"]:
        zuno = _task_zuno(task_name)
        live_read_tool = zuno.get("live_read_tool")
        if live_read_tool is None:
            continue
        checked += 1
        assert live_read_tool in zuno.get("allowed_tools", []), (
            f"{task_name}: live_read_tool {live_read_tool!r} is not in its own allowed_tools"
        )
    # No assertion on `checked` here (unlike the contract suite's non-
    # vacuous checks): zero tasks declaring live_read_tool is Finage's
    # genuine, documented state, not a suite bug.


def test_project_required_tasks_declare_a_project_scopable_resource() -> None:
    """ADR-0512/WP-55: a project_required task must declare at least one
    allowed_tools/allowed_knowledge entry capable of being scoped to a
    project - guards against declaring project_required on a task with
    nothing project-scopable to restrict. identify-business-ready-to-invoice
    and monthly-invoice-report both set project_required: true, so this
    exercises real content (not vacuously, unlike Arkos's copy of this
    same check)."""
    agent = _agent_zuno()
    checked = 0
    for task_name in agent["tasks"]:
        zuno = _task_zuno(task_name)
        if not zuno.get("project_required"):
            continue
        checked += 1
        has_scopable_resource = bool(zuno.get("allowed_tools")) or bool(zuno.get("allowed_knowledge"))
        assert has_scopable_resource, (
            f"{task_name}: project_required is set but it declares no allowed_tools/allowed_knowledge "
            "to scope to a project"
        )
    assert checked == 2, (
        f"expected exactly 2 project_required tasks (identify-business-ready-to-invoice, "
        f"monthly-invoice-report), found {checked} - update this assertion if that set changes"
    )


TESTS = [
    test_primary_task_is_declared_in_zuno_tasks,
    test_every_declared_task_has_a_task_file,
    test_live_read_tool_is_within_its_own_allowed_tools,
    test_project_required_tasks_declare_a_project_scopable_resource,
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
