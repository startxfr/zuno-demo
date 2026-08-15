#!/usr/bin/env python3
"""ADR-0342 (WP-30) acceptance tests: `GraphFactory`/`validate_shapes`
(app/graph/build.py) resolve a LangGraph workflow from
`AgentDefinition.graph_shape` alone, fail fast on an unknown/missing
shape, and generalize past exactly one hardcoded shape - proven here with
a minimal, test-only second shape registered from fixtures (Arkos's real
second shape lands in WP-31; this WP only proves the mechanism). Also
proves app/main.py's generic `{agent}` dispatch resolves an agent that was
never hardcoded into any route.

Same no-pytest/no-live-cluster style as tests/test_checkpointing.py. Run
directly:

    cd components/agent-runtime && python3 tests/test_graph_factory.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))
os.environ.setdefault(
    "KNOWLEDGE_POLICY_PATH", str(_REPO_ROOT / "policies" / "knowledge" / "knowledge-policy.yaml")
)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402

import app.main as main_module  # noqa: E402
from app.graph.build import GraphFactory, UnknownGraphShapeError, known_shapes, validate_shapes  # noqa: E402
from app.graph.shapes import SHAPE_BUILDERS  # noqa: E402
from app.graph.state import AgentState  # noqa: E402
from app.registry import AgentDefinition, AgentRegistry  # noqa: E402


def _build_fixture_echo(checkpointer):
    """The minimal test-only second shape the WP-30 brief asks for: a
    single node, structurally nothing like Tekos's retrieve/tool_call/
    reason/respond flow, proving GraphFactory doesn't special-case the
    real shape's topology."""

    async def echo_node(state):
        return {"reply": f"echo: {state['message']}", "citations": [], "source_mode": "none"}

    graph = StateGraph(AgentState)
    graph.add_node("echo", echo_node)
    graph.add_edge(START, "echo")
    graph.add_edge("echo", END)
    return graph.compile(checkpointer=checkpointer)


def _build_fixture_uppercase(checkpointer):
    """A second, distinct fixture shape - used only to prove that
    switching which shape an agent declares is a config change, not a
    GraphFactory code change."""

    async def upper_node(state):
        return {"reply": state["message"].upper(), "citations": [], "source_mode": "none"}

    graph = StateGraph(AgentState)
    graph.add_node("upper", upper_node)
    graph.add_edge(START, "upper")
    graph.add_edge("upper", END)
    return graph.compile(checkpointer=checkpointer)


def test_known_shapes_includes_the_real_tekos_shape() -> None:
    assert "retrieve_reason_respond" in set(known_shapes())


def test_validate_shapes_passes_for_the_real_registry() -> None:
    registry = AgentRegistry()
    assert not registry.load_errors, registry.load_errors
    validate_shapes(registry.all())  # must not raise


def test_validate_shapes_fails_closed_for_an_active_agent_with_no_shape() -> None:
    agent = AgentDefinition(name="fixture", status="active", preferred_classification="C1", rag_top_k=5)
    try:
        validate_shapes([agent])
        raise AssertionError("expected UnknownGraphShapeError")
    except UnknownGraphShapeError as exc:
        assert "fixture" in str(exc)


def test_validate_shapes_fails_closed_for_an_active_agent_with_an_unknown_shape() -> None:
    agent = AgentDefinition(
        name="fixture", status="active", preferred_classification="C1", rag_top_k=5, graph_shape="bogus_shape"
    )
    try:
        validate_shapes([agent])
        raise AssertionError("expected UnknownGraphShapeError")
    except UnknownGraphShapeError as exc:
        assert "bogus_shape" in str(exc)


def test_validate_shapes_tolerates_a_placeholder_with_no_shape() -> None:
    """A placeholder agent has no runtime workflow at all (ADR-0007) -
    it must not be forced to declare a shape it will never execute."""
    agent = AgentDefinition(name="fixture", status="placeholder", preferred_classification="C1", rag_top_k=5)
    validate_shapes([agent])  # must not raise


def test_validate_shapes_still_rejects_a_placeholder_naming_an_unknown_shape() -> None:
    """Defense in depth: unused-today metadata is still worth catching a
    typo in, even though nothing would build this agent's graph yet."""
    agent = AgentDefinition(
        name="fixture", status="placeholder", preferred_classification="C1", rag_top_k=5, graph_shape="bogus_shape"
    )
    try:
        validate_shapes([agent])
        raise AssertionError("expected UnknownGraphShapeError")
    except UnknownGraphShapeError:
        pass


def test_graph_factory_resolves_and_caches_the_real_tekos_shape() -> None:
    factory = GraphFactory(MemorySaver())
    first = factory.graph_for_shape("retrieve_reason_respond")
    second = factory.graph_for_shape("retrieve_reason_respond")
    assert first is second  # compiled once, reused - never rebuilt per call


def test_graph_factory_raises_for_an_unknown_shape_name() -> None:
    factory = GraphFactory(MemorySaver())
    try:
        factory.graph_for_shape("bogus_shape")
        raise AssertionError("expected UnknownGraphShapeError")
    except UnknownGraphShapeError:
        pass


def test_graph_factory_raises_for_an_agent_declaring_no_shape() -> None:
    factory = GraphFactory(MemorySaver())
    agent = AgentDefinition(name="fixture", status="active", preferred_classification="C1", rag_top_k=5)
    try:
        factory.graph_for(agent)
        raise AssertionError("expected UnknownGraphShapeError")
    except UnknownGraphShapeError:
        pass


async def test_two_distinct_shapes_serve_on_one_running_instance() -> None:
    """The core ADR-0342 acceptance bullet: GraphFactory builds/selects at
    least two distinct graph shapes from AgentDefinition alone, on the
    same running instance, with each producing genuinely different
    behavior - not just two names mapping to the same graph object."""
    SHAPE_BUILDERS["fixture_echo"] = _build_fixture_echo
    try:
        factory = GraphFactory(MemorySaver())

        registry = AgentRegistry()
        tekos = registry.get("tekos")
        assert tekos is not None and tekos.graph_shape == "retrieve_reason_respond"

        fixture_agent = AgentDefinition(
            name="fixture-agent",
            status="active",
            preferred_classification="C1",
            rag_top_k=5,
            graph_shape="fixture_echo",
        )

        tekos_graph = factory.graph_for(tekos)
        fixture_graph = factory.graph_for(fixture_agent)
        assert tekos_graph is not fixture_graph

        # The fixture shape actually runs its own, materially different
        # logic - proving this isn't just two names resolving to the same
        # compiled object.
        fixture_result = await fixture_graph.ainvoke(
            {
                "session_id": "s1",
                "user_sub": "alice",
                "groups": [],
                "bearer_token": "t",
                "message": "hello",
                "retrieved_docs": [],
                "tool_results": {},
                "errors": [],
            },
            config={"configurable": {"thread_id": "fixture-run-1"}},
        )
        assert fixture_result["reply"] == "echo: hello"
    finally:
        del SHAPE_BUILDERS["fixture_echo"]


async def test_switching_a_fixture_agents_shape_is_config_only() -> None:
    """ADR-0342 acceptance: "changing which graph shape an agent uses is a
    configuration/registration change, not a runtime code change to the
    other agent's path." Same GraphFactory instance, same agent name, only
    the declared `graph_shape` value changes between the two resolutions -
    no GraphFactory code is touched."""
    SHAPE_BUILDERS["fixture_echo"] = _build_fixture_echo
    SHAPE_BUILDERS["fixture_uppercase"] = _build_fixture_uppercase
    try:
        factory = GraphFactory(MemorySaver())
        fixture_agent = AgentDefinition(
            name="fixture-agent",
            status="active",
            preferred_classification="C1",
            rag_top_k=5,
            graph_shape="fixture_echo",
        )

        first_graph = factory.graph_for(fixture_agent)
        first_result = await first_graph.ainvoke(
            {
                "session_id": "s1",
                "user_sub": "alice",
                "groups": [],
                "bearer_token": "t",
                "message": "hello",
                "retrieved_docs": [],
                "tool_results": {},
                "errors": [],
            },
            config={"configurable": {"thread_id": "fixture-run-2"}},
        )
        assert first_result["reply"] == "echo: hello"

        # Only this line changes - a config value, not a code path.
        fixture_agent.graph_shape = "fixture_uppercase"

        second_graph = factory.graph_for(fixture_agent)
        assert second_graph is not first_graph
        second_result = await second_graph.ainvoke(
            {
                "session_id": "s1",
                "user_sub": "alice",
                "groups": [],
                "bearer_token": "t",
                "message": "hello",
                "retrieved_docs": [],
                "tool_results": {},
                "errors": [],
            },
            config={"configurable": {"thread_id": "fixture-run-3"}},
        )
        assert second_result["reply"] == "HELLO"
    finally:
        del SHAPE_BUILDERS["fixture_echo"]
        del SHAPE_BUILDERS["fixture_uppercase"]


def test_main_dispatch_resolves_an_agent_never_hardcoded_into_any_route() -> None:
    """app/main.py's `_active_agent_or_404` (used by both the chat and
    extract-memory routes) is the one and only agent-resolution point -
    proving it accepts a fixture agent injected purely through the
    registry (never named in main.py's own source) is the route-layer
    half of "no per-agent hardcoded route beyond generic dispatch"."""
    fixture_agent = AgentDefinition(
        name="fixture-agent-for-dispatch-test",
        status="active",
        preferred_classification="C1",
        rag_top_k=5,
        graph_shape="retrieve_reason_respond",
    )
    saved = dict(main_module._registry._agents)
    try:
        main_module._registry._agents["fixture-agent-for-dispatch-test"] = fixture_agent
        resolved = main_module._active_agent_or_404("fixture-agent-for-dispatch-test")
        assert resolved is fixture_agent

        try:
            main_module._active_agent_or_404("does-not-exist")
            raise AssertionError("expected an HTTPException for an unknown agent")
        except Exception as exc:  # HTTPException
            assert getattr(exc, "status_code", None) == 404, exc
    finally:
        main_module._registry._agents.clear()
        main_module._registry._agents.update(saved)


def test_main_dispatch_refuses_a_placeholder_agent_the_same_way() -> None:
    """A placeholder is a real, registered agent (ADR-0007) - it must 404
    exactly like an unknown name, never route to a graph that doesn't
    exist for it."""
    comage = main_module._registry.get("comage")
    assert comage is not None and comage.status == "placeholder"
    try:
        main_module._active_agent_or_404("comage")
        raise AssertionError("expected an HTTPException for a placeholder agent")
    except Exception as exc:  # HTTPException
        assert getattr(exc, "status_code", None) == 404, exc


TESTS = [
    test_known_shapes_includes_the_real_tekos_shape,
    test_validate_shapes_passes_for_the_real_registry,
    test_validate_shapes_fails_closed_for_an_active_agent_with_no_shape,
    test_validate_shapes_fails_closed_for_an_active_agent_with_an_unknown_shape,
    test_validate_shapes_tolerates_a_placeholder_with_no_shape,
    test_validate_shapes_still_rejects_a_placeholder_naming_an_unknown_shape,
    test_graph_factory_resolves_and_caches_the_real_tekos_shape,
    test_graph_factory_raises_for_an_unknown_shape_name,
    test_graph_factory_raises_for_an_agent_declaring_no_shape,
    test_two_distinct_shapes_serve_on_one_running_instance,
    test_switching_a_fixture_agents_shape_is_config_only,
    test_main_dispatch_resolves_an_agent_never_hardcoded_into_any_route,
    test_main_dispatch_refuses_a_placeholder_agent_the_same_way,
]


async def _run_all() -> int:
    failures = 0
    for test in TESTS:
        try:
            result = test()
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    return failures


def main() -> int:
    failures = asyncio.run(_run_all())
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
