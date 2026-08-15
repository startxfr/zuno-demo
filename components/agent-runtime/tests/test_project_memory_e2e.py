#!/usr/bin/env python3
"""ADR-0209 (WP-28) end-to-end (single-runtime) acceptance test: the Tekos
`demo-001` store-and-retrieve scenario required by both the WP-28 brief and
ADR-0209's acceptance criteria ("an end-to-end acceptance test exercises the
full scenario" - state facts in a session, extract them, retrieve them back
in a NEW session without the user repeating themselves).

Exercised entirely within this process against a `MemorySaver`-backed graph
(same pattern as tests/test_checkpointing.py) - the model (app/memory.py's
extraction call and app/graph/nodes.py's reason_node call, both routed
through the one shared ModelRouter instance) and the rag-service HTTP
boundary (app/clients/rag_client.py:search, app/clients/
project_memory_client.py:write_project_memory) are mocked, since neither a
live AI Gateway nor a live rag-project Postgres database exists in this
sandbox. What this test actually proves is the WIRING WP-28 added: a run's
project_id reaches extraction, extraction's output reaches the
project-memory write call with the right project_id/caller_sub, and a
second session's retrieve_node forwards knowledge.project + project_id +
caller_sub and folds whatever rag-service returns into the final reply's
citations - not that a real LLM correctly summarizes English text (that's
app/memory.py's own concern, covered in isolation by
tests/test_memory_extraction.py) or that Postgres actually persists rows
(rag-service's own tests/test_project_membership.py and
tests/test_write_path_invariant.py cover that side).

Run directly:

    cd components/agent-runtime && python3 tests/test_project_memory_e2e.py
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
from types import SimpleNamespace

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
# Both must be set before app.graph.nodes is ever imported in this process:
# it eagerly constructs an AgentRegistry (AGENTS_DIR) and a
# KnowledgePolicyStore (KNOWLEDGE_POLICY_PATH) at module level - see that
# file's own top-of-module comments. Without the second one, every
# knowledge-domain retrieval (including knowledge.project, this test's
# whole point) would fail closed with "knowledge policy file not found",
# same as production would with an unmounted ConfigMap.
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))
os.environ.setdefault(
    "KNOWLEDGE_POLICY_PATH", str(_REPO_ROOT / "policies" / "knowledge" / "knowledge-policy.yaml")
)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

from app.auth import CallerIdentity  # noqa: E402
from app.clients import project_memory_client  # noqa: E402
from app.clients.model_router import ProviderCandidate  # noqa: E402
from app.graph import nodes  # noqa: E402
from app.graph.shapes.retrieve_reason_respond import build as build_graph  # noqa: E402
from app.main import extract_memory_endpoint  # noqa: E402


def _identity(sub: str, groups) -> CallerIdentity:
    return CallerIdentity(sub=sub, groups=groups, raw_claims={}, token="fake-token")


class _FakeModelResult:
    def __init__(self, content: str):
        self.content = content


class _FakeGraphFactory:
    """Stands in for app.graph.build.GraphFactory (ADR-0342/WP-30) -
    these tests already hold one compiled graph directly, so this just
    hands it back regardless of which agent is asked for."""

    def __init__(self, graph):
        self._graph = graph

    def graph_for(self, agent_def):
        return self._graph


async def test_tekos_demo_001_store_and_retrieve_across_sessions() -> None:
    """The exact ADR-0209 scenario:

    1. Session 1 (project_id=demo-001): the user states a project fact.
    2. An explicit extraction call (session end) identifies it and writes
       it via rag-service's project-memory endpoint.
    3. Session 2 - a brand-new run_id/thread_id, same project_id, the user
       never repeats the fact - retrieve_node still surfaces it, because
       "storage" happened in step 2, not because the model remembered a
       prior turn.
    """
    graph = build_graph(MemorySaver())
    identity = _identity("alice", groups=["consultant"])

    # --- Simulated rag-service/project-memory backing store -----------------
    # A single mutable flag standing in for "has anything actually been
    # persisted for demo-001 yet" - lets session 1's search legitimately
    # return nothing (nothing written yet) while session 2's returns the
    # fact, the same store-then-retrieve ordering a real Postgres-backed
    # rag-service would enforce, without needing one here.
    backing_store = {"written_facts": None}

    write_calls = []

    async def fake_write_project_memory(**kwargs):
        write_calls.append(kwargs)
        backing_store["written_facts"] = kwargs["facts"]
        return {"facts_written": len(kwargs["facts"]), "memories_written": len(kwargs["memories"])}

    search_calls = []

    async def fake_search(**kwargs):
        search_calls.append(kwargs)
        domains = kwargs.get("domains") or []
        if "knowledge.project" in domains and backing_store["written_facts"]:
            return [
                {
                    "id": "proj-mem-1",
                    "source": "project-memory:demo-001",
                    "title": "cloud_provider",
                    "snippet": "The demo-001 project runs on AWS across three environments.",
                    "score": 0.95,
                    "classification": "C1",
                    "domain": "knowledge.project",
                    "stale": False,
                }
            ]
        return []

    async def fake_invoke(**kwargs):
        messages = kwargs.get("messages") or []
        system_text = messages[0].content if messages else ""
        if "durable, engagement-scoped memory" in system_text:
            # app/memory.py's extraction call.
            return (
                _FakeModelResult(
                    json.dumps(
                        {
                            "facts": [{"key": "cloud_provider", "value": "AWS"}],
                            "memories": [
                                {
                                    "kind": "fact",
                                    "text": "The demo-001 project runs on AWS across three environments.",
                                }
                            ],
                        }
                    )
                ),
                None,
            )
        # reason_node's own reply call.
        return _FakeModelResult("Noted - AWS, across three environments."), ProviderCandidate(name="ai-gateway")

    saved_search = nodes.search
    saved_invoke = nodes._model_router.invoke_with_fallback
    saved_write = project_memory_client.write_project_memory
    nodes.search = fake_search
    nodes._model_router.invoke_with_fallback = fake_invoke
    project_memory_client.write_project_memory = fake_write_project_memory

    try:
        # --- Session 1: state the fact, no retrievable project memory yet ---
        run_id_1 = "run-demo-001-session-1"
        config_1 = {"configurable": {"thread_id": run_id_1}}
        state_1 = {
            "session_id": "s1",
            "user_sub": "alice",
            "groups": ["consultant"],
            "bearer_token": "t",
            "message": "We run this project on AWS, across three environments: dev, staging, prod.",
            "request_id": "req-1",
            "project_id": "demo-001",
            "retrieved_docs": [],
            "tool_results": {},
            "errors": [],
        }
        final_1 = await graph.ainvoke(state_1, config=config_1)
        assert final_1["reply"]
        # Nothing durable has been extracted/written yet - this turn's own
        # retrieval must not have found anything under knowledge.project.
        assert not any(doc.get("domain") == "knowledge.project" for doc in final_1["retrieved_docs"])

        # --- Explicit extraction (session end), reusing _resolve_run_id's
        # ownership check by construction - same run_id, same identity. ---
        fake_request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(graph_factory=_FakeGraphFactory(graph)))
        )
        extraction_result = await extract_memory_endpoint(
            agent="tekos", run_id=run_id_1, request=fake_request, identity=identity
        )
        assert extraction_result["facts_written"] == 1
        assert extraction_result["memories_written"] == 1
        assert len(write_calls) == 1
        assert write_calls[0]["project_id"] == "demo-001"
        assert write_calls[0]["caller_sub"] == "alice"
        assert write_calls[0]["facts"] == [{"key": "cloud_provider", "value": "AWS"}]

        # --- Session 2: a brand-new run/thread, same project, fact never
        # restated by the user. ---
        run_id_2 = "run-demo-001-session-2"
        config_2 = {"configurable": {"thread_id": run_id_2}}
        state_2 = {
            "session_id": "s2",
            "user_sub": "alice",
            "groups": ["consultant"],
            "bearer_token": "t",
            "message": "What cloud provider does this project use?",
            "request_id": "req-2",
            "project_id": "demo-001",
            "retrieved_docs": [],
            "tool_results": {},
            "errors": [],
        }
        final_2 = await graph.ainvoke(state_2, config=config_2)

        # The domain fan-out actually included knowledge.project, scoped to
        # this exact project/caller (ADR-0209's fail-closed membership check
        # requires both) - not just that *some* retrieval call happened.
        project_calls = [c for c in search_calls if "knowledge.project" in (c.get("domains") or [])]
        assert project_calls, "retrieve_node never requested knowledge.project"
        assert project_calls[-1]["project_id"] == "demo-001"
        assert project_calls[-1]["caller_sub"] == "alice"

        # And the previously-written fact actually reached the final
        # answer's context/citations - "retrieve these facts without the
        # user repeating them", not just that the right HTTP call shape
        # was built.
        assert any(doc.get("domain") == "knowledge.project" for doc in final_2["retrieved_docs"])
        assert any(c["title"] == "cloud_provider" for c in final_2["citations"])
        assert final_2["source_mode"] == "indexed"
    finally:
        nodes.search = saved_search
        nodes._model_router.invoke_with_fallback = saved_invoke
        project_memory_client.write_project_memory = saved_write


async def test_extraction_is_refused_for_a_run_with_no_project_id() -> None:
    """ADR-0209: "a run with none has nothing to extract INTO" (see
    app/main.py:extract_memory_endpoint's own docstring) - a plain
    knowledge.tech-only Tekos run must not be extractable, distinguishing
    this from an accidental default-bucket behavior."""
    graph = build_graph(MemorySaver())
    identity = _identity("alice", groups=["consultant"])

    saved_search = nodes.search
    saved_invoke = nodes._model_router.invoke_with_fallback

    async def fake_search(**kwargs):
        return []

    async def fake_invoke(**kwargs):
        # No live AI Gateway in this sandbox - reason_node must not make a
        # real network call just because this test's focus is the
        # extraction endpoint, not the chat turn that precedes it.
        return _FakeModelResult("ok"), ProviderCandidate(name="ai-gateway")

    nodes.search = fake_search
    nodes._model_router.invoke_with_fallback = fake_invoke
    try:
        run_id = "run-no-project"
        config = {"configurable": {"thread_id": run_id}}
        await graph.ainvoke(
            {
                "session_id": "s1",
                "user_sub": "alice",
                "groups": ["consultant"],
                "bearer_token": "t",
                "message": "how do I configure a ServingRuntime",
                "request_id": "req-1",
                "project_id": None,
                "retrieved_docs": [],
                "tool_results": {},
                "errors": [],
            },
            config=config,
        )

        fake_request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(graph_factory=_FakeGraphFactory(graph)))
        )
        try:
            await extract_memory_endpoint(agent="tekos", run_id=run_id, request=fake_request, identity=identity)
            raise AssertionError("expected an HTTPException for a run with no project_id")
        except Exception as exc:  # HTTPException
            assert getattr(exc, "status_code", None) == 400, exc
    finally:
        nodes.search = saved_search
        nodes._model_router.invoke_with_fallback = saved_invoke


TESTS = [
    test_tekos_demo_001_store_and_retrieve_across_sessions,
    test_extraction_is_refused_for_a_run_with_no_project_id,
]


async def _run_all() -> int:
    failures = 0
    for test in TESTS:
        try:
            await test()
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
