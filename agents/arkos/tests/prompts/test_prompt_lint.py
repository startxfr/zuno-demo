#!/usr/bin/env python3
"""ADR-0504 prompts/ suite: prompt lint for Arkos - every prompt file
carries the OKF `type: prompt` frontmatter Agent Runtime's registry
requires (the WP-41 generator-bug class), every prompt is referenced by a
task (either as its primary prompt or one of its zuno.prompts slots), and
no orphaned prompt files exist under prompts/. Static repository checks
only.

Run directly (from anywhere) or via
platform/okf/run_agent_contract_tests.py:

    python3 agents/arkos/tests/prompts/test_prompt_lint.py
"""
from __future__ import annotations

import pathlib
import sys

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
AGENT_DIR = REPO_ROOT / "agents" / "arkos"
PROMPTS_DIR = AGENT_DIR / "prompts"


def _split_frontmatter(path: pathlib.Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    assert len(parts) >= 3, f"{path}: expected a leading '---' YAML frontmatter block"
    return yaml.safe_load(parts[1]) or {}, parts[2].strip()


def _agent_zuno() -> dict:
    fm, _ = _split_frontmatter(AGENT_DIR / "agent.okf.md")
    return fm["zuno"]


def _real_prompt_files() -> list:
    # README.md is a stub, not a prompt bundle - excluded the same way
    # app/registry.py's own loader only ever globs <task>.md/
    # <task>--<slot>.md filenames, never README.md.
    return sorted(p for p in PROMPTS_DIR.glob("*.md") if p.name != "README.md")


def _expected_prompt_paths() -> set:
    """Every filename app/registry.py's _load_task would look for, given
    the real zuno.tasks list - the primary <task>.md convention plus
    <task>--<slot>.md for each declared prompts slot (ADR-0419)."""
    agent = _agent_zuno()
    expected = set()
    for task_name in agent["tasks"]:
        task_fm, _ = _split_frontmatter(AGENT_DIR / "tasks" / f"{task_name}.md")
        expected.add(f"{task_name}.md")
        for slot_name in ((task_fm.get("zuno") or {}).get("prompts") or {}):
            expected.add(f"{task_name}--{slot_name}.md")
    return expected


def test_every_prompt_file_has_type_prompt_frontmatter() -> None:
    files = _real_prompt_files()
    assert files, "no prompt files found under prompts/ - suite would be vacuous"
    for path in files:
        fm, _ = _split_frontmatter(path)
        assert fm.get("type") == "prompt", f"{path.name}: expected frontmatter 'type: prompt', got {fm.get('type')!r}"


def test_every_prompt_file_is_referenced_by_a_task_or_prompt_slot() -> None:
    """Guards against an orphaned prompt file (typo'd name, leftover from
    a rename) that app/registry.py would silently never load - the same
    class of drift ADR-0419's own graceful-degradation posture makes easy
    to introduce unnoticed."""
    expected = _expected_prompt_paths()
    for path in _real_prompt_files():
        assert path.name in expected, (
            f"{path.name} exists under prompts/ but no task/prompt-slot declaration references it "
            f"(expected one of: {sorted(expected)})"
        )


def test_every_declared_prompt_reference_has_a_real_file() -> None:
    """The inverse of the orphan check above: every <task>.md/
    <task>--<slot>.md filename the bundle's own declarations imply must
    actually exist - a missing primary prompt is a hard RuntimeError at
    Agent Runtime import time (see arkos_nodes.py's fail-fast guards for
    _DRAFT_TASK/_WORKSHOP_TASK/_STRUCTURE_DEMO_TASK), and a missing slot
    prompt silently degrades to reflect_node's hardcoded fallback
    (ADR-0419's accepted risk) - both worth catching here, statically,
    before either happens at runtime."""
    agent = _agent_zuno()
    for task_name in agent["tasks"]:
        primary_path = PROMPTS_DIR / f"{task_name}.md"
        # write-code is the one task that deliberately has no primary
        # prompt file (its system prompt is still a Python literal in
        # code_node) - not a drift, an explicitly documented exception
        # (see tasks/structure-demo.md's own note contrasting the two).
        if task_name == "write-code":
            continue
        assert primary_path.is_file(), f"{task_name}: zuno.tasks declares it but {primary_path} is missing"

        task_fm, _ = _split_frontmatter(AGENT_DIR / "tasks" / f"{task_name}.md")
        for slot_name in ((task_fm.get("zuno") or {}).get("prompts") or {}):
            slot_path = PROMPTS_DIR / f"{task_name}--{slot_name}.md"
            assert slot_path.is_file(), (
                f"{task_name}: declares prompts.{slot_name} but {slot_path} is missing"
            )


TESTS = [
    test_every_prompt_file_has_type_prompt_frontmatter,
    test_every_prompt_file_is_referenced_by_a_task_or_prompt_slot,
    test_every_declared_prompt_reference_has_a_real_file,
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
