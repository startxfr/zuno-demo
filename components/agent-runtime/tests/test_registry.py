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
    # ADR-0203: declared_knowledge() is the union of every task's own
    # allowed_knowledge, mirroring declared_tools() exactly - there is no
    # separate agent-level field.
    assert set(tekos.declared_knowledge()) == {"knowledge.tech", "knowledge.project"}

    task = tekos.tasks["answer-technical-question"]
    assert task.allowed_tools == ["search_confluence", "web_search"]
    # ADR-0209 (WP-28): knowledge.project added alongside knowledge.tech -
    # the task can retrieve project memory too, gated per-turn on an
    # actual project_id being present (app/graph/nodes.py:retrieve_node).
    assert task.allowed_knowledge == ["knowledge.tech", "knowledge.project"]
    assert task.prompt and "Tekos" in task.prompt


def test_placeholder_agents_declare_their_real_tool_ceiling() -> None:
    """Arkos, Comage, Advantage and Finage all have real task bundles and
    graph shapes merged (WP-31/WP-33/WP-35/WP-36), but `status`
    deliberately stays `placeholder` for each until the operator confirms
    its own live acceptance gate passes (each WP's own Status-updates
    section) - they legitimately DO declare real tools while still
    reporting placeholder status. Finage completes the four-agent
    generalization (ADR-0326): every non-Tekos agent now has a real
    bundle, so there is no longer a "still-genuinely-placeholder, declares
    no tools" case left to test."""
    registry = AgentRegistry(agents_dir=str(REAL_AGENTS_DIR))

    arkos = registry.get("arkos")
    assert arkos is not None
    assert arkos.status == "placeholder"
    assert arkos.declared_tools() == [
        "confluence.page.read",
        "confluence.page.search",
        "drive.document.create",
        "drive.document.update",
    ]

    comage = registry.get("comage")
    assert comage is not None
    assert comage.status == "placeholder"
    assert comage.declared_tools() == [
        "salesforce.opportunity.read",
        "web_search",
        "salesforce.opportunity.update",
        "sxa.opportunity.search",
        "sxa.aggregate.revenue-by-year",
        "list_drive_files",
        "read_gmail",
    ]

    advantage = registry.get("advantage")
    assert advantage is not None
    assert advantage.status == "placeholder"
    assert advantage.declared_tools() == [
        "web_search",
        "list_drive_files",
        "read_gmail",
    ]

    finage = registry.get("finage")
    assert finage is not None
    assert finage.status == "placeholder"
    assert finage.declared_tools() == [
        "web_search",
        "sxa.customer.read",
        "sxa.quote.read",
        "sxa.aggregate.revenue-by-year",
        "sxa.record.lookup",
        "list_drive_files",
        "read_gmail",
    ]


def test_genuine_placeholder_agents_declare_no_tools() -> None:
    """ADR-0349 §6 resurrected the case this file's own history says
    briefly ceased to exist (WP-36a's rename note): soursage and cognos
    are GENUINELY-placeholder agents - identity footprint + coming-soon
    bundle only, no runtime, no chart. A placeholder of that original
    kind has zero tool-call capability by construction (ADR-0036), and
    no graph shape either (nothing for GraphFactory to build)."""
    registry = AgentRegistry(agents_dir=str(REAL_AGENTS_DIR))

    for name in ("soursage", "cognos"):
        agent = registry.get(name)
        assert agent is not None, f"{name} bundle failed to load"
        assert agent.status == "placeholder"
        assert agent.declared_tools() == [], f"{name} must declare zero tools while genuinely placeholder"
        assert agent.graph_shape is None, f"{name} must declare no graph shape (no runtime workflow exists)"


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

_FIXTURE_TASK_WITH_PROMPT_SLOT = """---
okf_version: v0.2
type: task
title: Do a thing
zuno:
  allowed_tools:
    - search_confluence
  prompts:
    reflect:
      classification_ceiling: C2
    orphan: {}
---

Do a thing.
"""

_FIXTURE_REFLECT_PROMPT_MD = """---
okf_version: v0.2
type: prompt
title: Fixture reflect prompt
---

Review your own output.
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
        # ADR-0416: absent zuno.model.local_only defaults False.
        assert agent_v1.local_only is False

        # Edit only the bundle - no Python code changes - then reload via a
        # fresh AgentRegistry (matching how a redeploy picks up a bundle
        # change, per this ADR's own operational model).
        (agent_dir / "tasks" / "do-a-thing.md").write_text(_FIXTURE_TASK_V2, encoding="utf-8")

        registry_v2 = AgentRegistry(agents_dir=str(agents_dir))
        agent_v2 = registry_v2.get("fixture-agent")
        assert agent_v2.declared_tools() == ["search_confluence", "web_search"]

        shutil.rmtree(agent_dir, ignore_errors=True)


def test_prompt_slots_load_declared_ceiling_and_prompt_text() -> None:
    """ADR-0419: a task's zuno.prompts entries resolve to PromptSlot
    objects, each with its own classification_ceiling and prompt text
    loaded from <task-name>--<slot>.md - independent of the task's own
    primary prompt file."""
    with tempfile.TemporaryDirectory() as tmp:
        agents_dir = pathlib.Path(tmp)
        agent_dir = agents_dir / "fixture-agent"
        (agent_dir / "tasks").mkdir(parents=True)
        (agent_dir / "prompts").mkdir(parents=True)
        (agent_dir / "agent.okf.md").write_text(_FIXTURE_AGENT_MD, encoding="utf-8")
        (agent_dir / "tasks" / "do-a-thing.md").write_text(_FIXTURE_TASK_WITH_PROMPT_SLOT, encoding="utf-8")
        (agent_dir / "prompts" / "do-a-thing--reflect.md").write_text(_FIXTURE_REFLECT_PROMPT_MD, encoding="utf-8")

        try:
            registry = AgentRegistry(agents_dir=str(agents_dir))
            assert not registry.load_errors, registry.load_errors
            task = registry.get("fixture-agent").tasks["do-a-thing"]

            reflect = task.prompts.get("reflect")
            assert reflect is not None
            assert reflect.classification_ceiling == "C2"
            assert reflect.prompt == "Review your own output."

            # Declared in frontmatter but no do-a-thing--orphan.md file on
            # disk - resolves to a present slot with prompt=None, the same
            # silent-degradation behavior the primary prompt already has
            # for a missing file (never a load error).
            orphan = task.prompts.get("orphan")
            assert orphan is not None
            assert orphan.classification_ceiling is None
            assert orphan.prompt is None
        finally:
            shutil.rmtree(agent_dir, ignore_errors=True)


def test_task_with_no_prompts_key_has_an_empty_prompts_dict() -> None:
    """Backward compatibility: every task that doesn't declare zuno.prompts
    (i.e. every task in the repo except arkos's draft-architecture-
    testimonial) resolves to an empty dict, not None or an error."""
    with tempfile.TemporaryDirectory() as tmp:
        agents_dir = pathlib.Path(tmp)
        agent_dir = agents_dir / "fixture-agent"
        (agent_dir / "tasks").mkdir(parents=True)
        (agent_dir / "agent.okf.md").write_text(_FIXTURE_AGENT_MD, encoding="utf-8")
        (agent_dir / "tasks" / "do-a-thing.md").write_text(_FIXTURE_TASK_V1, encoding="utf-8")

        try:
            registry = AgentRegistry(agents_dir=str(agents_dir))
            task = registry.get("fixture-agent").tasks["do-a-thing"]
            assert task.prompts == {}
        finally:
            shutil.rmtree(agent_dir, ignore_errors=True)


def test_finage_declares_local_only_from_its_real_bundle() -> None:
    """ADR-0416 sanity check against the actual checked-in bundle: Finage
    must never be routable to an external model, at any classification -
    every other agent defaults to local_only False."""
    registry = AgentRegistry(agents_dir=str(REAL_AGENTS_DIR))
    finage = registry.get("finage")
    assert finage is not None
    assert finage.local_only is True

    tekos = registry.get("tekos")
    assert tekos is not None
    assert tekos.local_only is False


TESTS = [
    test_tekos_loads_from_the_real_bundle,
    test_placeholder_agents_declare_their_real_tool_ceiling,
    test_genuine_placeholder_agents_declare_no_tools,
    test_changing_the_bundle_changes_resolved_behavior_with_no_code_change,
    test_prompt_slots_load_declared_ceiling_and_prompt_text,
    test_task_with_no_prompts_key_has_an_empty_prompts_dict,
    test_finage_declares_local_only_from_its_real_bundle,
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
