#!/usr/bin/env python3
"""ADR-0504 contract suite: Arkos bundle-level self-consistency. Static
repository checks only - no cluster, no credentials, no model calls (see
tests/contract/README.md's three-layer boundary). First real suite filled
under this structure (WP-9, Arkos's Stage 2 promotion prep) - there is no
prior agent's suite to mirror, so shape/conventions here are new.

Run directly (from anywhere - resolves the repo root from __file__):

    python3 agents/arkos/tests/contract/test_bundle_self_consistency.py

Also picked up and executed by platform/okf/run_agent_contract_tests.py.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
AGENT_DIR = REPO_ROOT / "agents" / "arkos"
TOOL_POLICY_PATH = REPO_ROOT / "policies" / "tools" / "tool-policy.yaml"
KNOWLEDGE_POLICY_PATH = REPO_ROOT / "policies" / "knowledge" / "knowledge-policy.yaml"

# ADR-0349: the business role gating an already-entitled Arkos session -
# see agent.okf.md's own body prose ("DATs are still reviewed at board
# level as a business process, but the role gating an already-entitled
# Arkos session is consultant").
ARKOS_BUSINESS_ROLE = "consultant"


def _split_frontmatter(path: pathlib.Path) -> dict:
    """Same small parsing logic app/registry.py's _split_frontmatter has -
    duplicated here rather than imported, matching this repo's established
    convention for independently-lifecycled small parsers (see that
    module's own docstring)."""
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    assert len(parts) >= 3, f"{path}: expected a leading '---' YAML frontmatter block"
    return yaml.safe_load(parts[1]) or {}


def _arkos_tasks() -> dict:
    agent_fm = _split_frontmatter(AGENT_DIR / "agent.okf.md")
    task_names = agent_fm["zuno"]["tasks"]
    tasks = {}
    for name in task_names:
        tasks[name] = _split_frontmatter(AGENT_DIR / "tasks" / f"{name}.md")
    return tasks


def _tool_policy_by_name() -> dict:
    """Indexes by both `tool` (legacy MCP name, e.g. search_confluence)
    and `capability` (the OKF-declared name, e.g. confluence.page.search)
    - mirrors platform/okf/generate_authorization_matrix.py's own
    _load_tool_policy() exactly, since a task's allowed_tools entries are
    capability names and may not equal the policy row's `tool` key."""
    data = yaml.safe_load(TOOL_POLICY_PATH.read_text(encoding="utf-8"))
    by_name = {}
    for entry in data["tools"]:
        for key in ("tool", "capability"):
            if entry.get(key):
                by_name[entry[key]] = entry
    return by_name


def test_every_allowed_tool_resolves_with_the_consultant_role() -> None:
    tool_policy = _tool_policy_by_name()
    tasks = _arkos_tasks()
    checked = 0
    for task_name, fm in tasks.items():
        for tool in (fm.get("zuno") or {}).get("allowed_tools", []):
            entry = tool_policy.get(tool)
            assert entry is not None, f"{task_name}: allowed_tools entry {tool!r} has no tool-policy.yaml row"
            allowed_groups = entry.get("allowed_groups", [])
            assert ARKOS_BUSINESS_ROLE in allowed_groups, (
                f"{task_name}: {tool!r}'s allowed_groups {allowed_groups} does not include "
                f"{ARKOS_BUSINESS_ROLE!r}"
            )
            checked += 1
    assert checked > 0, "no allowed_tools entries found across arkos's tasks - suite would be vacuous"


def test_every_allowed_knowledge_domain_resolves_with_the_consultant_role() -> None:
    domains = yaml.safe_load(KNOWLEDGE_POLICY_PATH.read_text(encoding="utf-8"))["domains"]
    tasks = _arkos_tasks()
    checked = 0
    for task_name, fm in tasks.items():
        for domain in (fm.get("zuno") or {}).get("allowed_knowledge", []):
            entry = domains.get(domain)
            assert entry is not None, f"{task_name}: allowed_knowledge entry {domain!r} has no knowledge-policy.yaml domain"
            allowed_groups = entry.get("allowed_groups", [])
            assert ARKOS_BUSINESS_ROLE in allowed_groups, (
                f"{task_name}: {domain!r}'s allowed_groups {allowed_groups} does not include "
                f"{ARKOS_BUSINESS_ROLE!r}"
            )
            checked += 1
    assert checked > 0, "no allowed_knowledge entries found across arkos's tasks - suite would be vacuous"


def test_authorization_matrix_is_current() -> None:
    """ADR-0503: the generated matrix in agent.okf.md must match what
    generate_authorization_matrix.py --check would (re)produce - a stale
    matrix (e.g. a task added without regenerating) is exactly the drift
    this check exists to catch before promotion."""
    result = subprocess.run(
        [sys.executable, "platform/okf/generate_authorization_matrix.py", "--check", "arkos"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"agent.okf.md's authorization matrix is stale - run "
        f"'python3 platform/okf/generate_authorization_matrix.py'\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_deployment_snapshot_is_current() -> None:
    """ADR-0503: same currency check as the matrix above, for the
    generated CR snapshot."""
    result = subprocess.run(
        [sys.executable, "platform/okf/generate_deployment_snapshot.py", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"a deployment snapshot is stale - run "
        f"'python3 platform/okf/generate_deployment_snapshot.py'\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


TESTS = [
    test_every_allowed_tool_resolves_with_the_consultant_role,
    test_every_allowed_knowledge_domain_resolves_with_the_consultant_role,
    test_authorization_matrix_is_current,
    test_deployment_snapshot_is_current,
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
