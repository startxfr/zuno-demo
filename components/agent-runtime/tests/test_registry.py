#!/usr/bin/env python3
"""ADR-0039 acceptance test: proves Agent Runtime behavior (allowed tools,
model classification, RAG top_k, prompt) is driven by the checked-in OKF
bundle (ADR-0038), not hardcoded Python - "a v0 acceptance test must prove
that changing an agent definition changes allowed tools/model/context
without modifying runtime source code" (ADR-0039 Operational
considerations).

No live cluster needed - pure local file loading, same style as
evaluations/tekos/security_checks.py's config-consistency checks. Run
directly:

    cd components/agent-runtime && python3 tests/test_registry.py
"""
from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

from app.registry import AgentRegistry  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
REAL_AGENTS_DIR = REPO_ROOT / "agents"


def test_tekos_loads_from_the_real_bundle() -> None:
    """Sanity check against the actual checked-in agents/tekos/ bundle."""
    registry = AgentRegistry(agents_dir=str(REAL_AGENTS_DIR))
    assert not registry.load_errors, registry.load_errors

    tekos = registry.get("tekos")
    assert tekos is not None
    assert tekos.status == "active"
    assert tekos.preferred_classification == "C1"
    assert tekos.rag_top_k == 5
    assert set(tekos.declared_tools()) == {"search_confluence", "web_search", "list_drive_files"}

    task = tekos.tasks["answer-technical-question"]
    assert task.allowed_tools == ["search_confluence", "web_search"]
    assert task.prompt and "Tekos" in task.prompt


def test_placeholder_agents_declare_no_tools() -> None:
    registry = AgentRegistry(agents_dir=str(REAL_AGENTS_DIR))
    for name in ("comage", "advantage", "finage", "arkos"):
        agent = registry.get(name)
        assert agent is not None, name
        assert agent.status == "placeholder"
        assert agent.declared_tools() == []


_FIXTURE_TASK_V1 = """---
okf_version: v0.2
type: task
title: Do a thing
zuno:
  allowed_tools:
    - search_confluence
---

Do a thing.
"""

_FIXTURE_TASK_V2 = """---
okf_version: v0.2
type: task
title: Do a thing
zuno:
  allowed_tools:
    - search_confluence
    - web_search
---

Do a thing, now also searching the web.
"""

_FIXTURE_AGENT_MD = """---
okf_version: v0.2
type: agent
title: Fixture Agent
description: A fixture agent for ADR-0039's acceptance test.
zuno:
  name: fixture-agent
  status: active
  tasks:
    - do-a-thing
  rag:
    top_k: 3
  model:
    preferred_classification: C1
  access:
    groups:
      - agent_fixture_agent
  ui:
    displayName: Fixture
    tileDescription: Fixture.
    color: "#000000"
    icon: code
---

Fixture agent body.
"""


def test_changing_the_bundle_changes_resolved_behavior_with_no_code_change() -> None:
    """The core ADR-0039 claim: same AgentRegistry code, different bundle
    content, different resolved AgentDefinition - proving runtime behavior
    is config-driven, not hardcoded, independent of Tekos's specific bundle.
    """
    with tempfile.TemporaryDirectory() as tmp:
        agents_dir = pathlib.Path(tmp)
        agent_dir = agents_dir / "fixture-agent"
        (agent_dir / "tasks").mkdir(parents=True)
        (agent_dir / "agent.okf.md").write_text(_FIXTURE_AGENT_MD, encoding="utf-8")
        (agent_dir / "tasks" / "do-a-thing.md").write_text(_FIXTURE_TASK_V1, encoding="utf-8")

        registry_v1 = AgentRegistry(agents_dir=str(agents_dir))
        assert not registry_v1.load_errors, registry_v1.load_errors
        agent_v1 = registry_v1.get("fixture-agent")
        assert agent_v1.declared_tools() == ["search_confluence"]
        assert agent_v1.rag_top_k == 3

        # Edit only the bundle - no Python code changes - then reload via a
        # fresh AgentRegistry (matching how a redeploy picks up a bundle
        # change, per this ADR's own operational model).
        (agent_dir / "tasks" / "do-a-thing.md").write_text(_FIXTURE_TASK_V2, encoding="utf-8")

        registry_v2 = AgentRegistry(agents_dir=str(agents_dir))
        agent_v2 = registry_v2.get("fixture-agent")
        assert agent_v2.declared_tools() == ["search_confluence", "web_search"]

        shutil.rmtree(agent_dir, ignore_errors=True)


TESTS = [
    test_tekos_loads_from_the_real_bundle,
    test_placeholder_agents_declare_no_tools,
    test_changing_the_bundle_changes_resolved_behavior_with_no_code_change,
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
