#!/usr/bin/env python3
"""ADR-0342 (WP-31) unit tests for app/graph/arkos_nodes.py's pure/testable
units: topic extraction, source-mode computation and citation assembly.
The full plan -> retrieve -> draft -> write pipeline (incl. Confluence
folding and Drive write) is exercised end to end by
tests/test_project_memory_e2e.py's cross-agent scenario instead - these
are the narrower, faster-to-run units that don't need a mocked HTTP
round-trip. Same no-pytest/no-live-cluster style as
tests/test_retrieve_metadata.py.

Run directly:

    cd components/agent-runtime && python3 tests/test_arkos_nodes.py
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

from app.clients.model_router import ModelRouterError, ProviderCandidate  # noqa: E402
from app.graph import arkos_nodes, nodes  # noqa: E402


class _FakeModelResult:
    def __init__(self, content: str, tool_calls=None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


def test_extract_topic_from_a_dat_request() -> None:
    topic = arkos_nodes._extract_topic("Draft a DAT for the OpenShift AI GPU sizing project")
    assert topic == "the OpenShift AI GPU sizing project"


def test_extract_topic_accepts_the_full_phrase_too() -> None:
    topic = arkos_nodes._extract_topic(
        "Create a Design & Architecture Testimonial for the Keycloak SSO migration"
    )
    assert topic == "the Keycloak SSO migration"


def test_extract_topic_falls_back_to_the_whole_message_when_unmatched() -> None:
    message = "Summarize what a DAT is in one sentence."
    assert arkos_nodes._extract_topic(message) == message


def test_source_mode_indexed_only() -> None:
    state = {"retrieved_docs": [{"source": "x", "title": "X"}], "tool_results": {}}
    assert arkos_nodes._compute_source_mode(state) == "indexed"


def test_source_mode_live_only() -> None:
    state = {
        "retrieved_docs": [],
        "tool_results": {"confluence.page.search": {"result": {"results": [{"title": "Y", "url": "y"}]}}},
    }
    assert arkos_nodes._compute_source_mode(state) == "live"


def test_source_mode_both() -> None:
    state = {
        "retrieved_docs": [{"source": "x", "title": "X"}],
        "tool_results": {"confluence.page.search": {"result": {"results": [{"title": "Y", "url": "y"}]}}},
    }
    assert arkos_nodes._compute_source_mode(state) == "both"


def test_source_mode_none_when_nothing_contributed() -> None:
    state = {"retrieved_docs": [], "tool_results": {}}
    assert arkos_nodes._compute_source_mode(state) == "none"


def test_source_mode_ignores_an_empty_confluence_result_as_not_live() -> None:
    state = {
        "retrieved_docs": [{"source": "x", "title": "X"}],
        "tool_results": {"confluence.page.search": {"result": {"results": []}}},
    }
    assert arkos_nodes._compute_source_mode(state) == "indexed"


def test_citations_include_both_rag_docs_and_confluence_results() -> None:
    state = {
        "retrieved_docs": [{"source": "rag:doc1", "title": "Doc One"}],
        "tool_results": {
            "confluence.page.search": {
                "result": {"results": [{"title": "Confluence Page", "url": "https://confluence.example/x"}]}
            }
        },
    }
    citations = arkos_nodes._citations(state)
    assert {"source": "rag:doc1", "title": "Doc One"} in citations
    assert {"source": "https://confluence.example/x", "title": "Confluence Page"} in citations


def test_drive_result_url_unwraps_the_gateway_result_envelope() -> None:
    assert arkos_nodes._drive_result_url({"result": {"url": "https://docs.google.com/x"}}) == "https://docs.google.com/x"


def test_drive_result_url_falls_back_to_a_flat_shape() -> None:
    assert arkos_nodes._drive_result_url({"url": "https://docs.google.com/y"}) == "https://docs.google.com/y"


def test_drive_result_url_is_none_when_absent() -> None:
    assert arkos_nodes._drive_result_url({"result": {}}) is None


# --------------------------------------------------------------------------
# ADR-0416: reflect_node's fixed-C2-ceiling override
# --------------------------------------------------------------------------


async def test_reflect_node_uses_a_fixed_c2_ceiling_regardless_of_effective_classification() -> None:
    """Arkos's effective_classification is C3 for essentially every real
    turn (it starts at the agent's C3 seed and only escalates,
    ADR-0034) - reflect_node must still evaluate its own call at C2, not
    state['effective_classification'], since that's the whole point of
    the ADR-0416 scoped exception."""
    captured = {}

    async def fake_invoke(**kwargs):
        captured.update(kwargs)
        return _FakeModelResult("a refined draft"), ProviderCandidate(name="ai-gateway")

    saved_invoke = arkos_nodes._model_router.invoke_with_fallback
    try:
        arkos_nodes._model_router.invoke_with_fallback = fake_invoke
        state = {
            "document_draft": "the original draft",
            "effective_classification": "C3",
            "local_only_required": False,
            "bearer_token": "t",
            "request_id": "req-1",
        }
        result = await arkos_nodes.reflect_node(state)
    finally:
        arkos_nodes._model_router.invoke_with_fallback = saved_invoke

    assert captured, "reflect_node never called the model router"
    assert captured["classification"] == "C2", "must not inherit the turn's escalated C3"
    assert captured["local_only"] is False
    # ADR-0215: must never stream visibly - draft_node's own call already
    # streamed the pre-refinement draft to the user in the same graph run;
    # without this tag app/main.py's _stream_chat would forward this
    # call's tokens too, showing the user the draft twice concatenated.
    assert captured["tags"] == ["zuno-internal"]
    assert result["document_draft"] == "a refined draft"


async def test_reflect_node_still_honors_local_only_required() -> None:
    """The C2 ceiling overrides classification ESCALATION only, never the
    separate ADR-0035 source-level restriction - a turn where a source
    forbade its own influence from reaching any external model must stay
    local even though reflect_node's own ceiling is C2."""
    captured = {}

    async def fake_invoke(**kwargs):
        captured.update(kwargs)
        return _FakeModelResult("a refined draft"), ProviderCandidate(name="ai-gateway")

    saved_invoke = arkos_nodes._model_router.invoke_with_fallback
    try:
        arkos_nodes._model_router.invoke_with_fallback = fake_invoke
        state = {
            "document_draft": "the original draft",
            "effective_classification": "C3",
            "local_only_required": True,
            "bearer_token": "t",
            "request_id": "req-1",
        }
        await arkos_nodes.reflect_node(state)
    finally:
        arkos_nodes._model_router.invoke_with_fallback = saved_invoke

    assert captured["local_only"] is True


async def test_reflect_node_is_a_noop_without_a_draft() -> None:
    """Must still write a real key even on the no-op path - a bare `{}`
    passes this direct-call test but violates LangGraph's own "a node must
    write to at least one state key" runtime contract once this node runs
    inside the actual compiled StateGraph (unconditionally reachable from
    draft_node via the plan_draft_write shape's `draft -> reflect` edge).
    See test_draft_node_then_reflect_node_survives_an_empty_image_caption
    below for the real sequence that used to crash on this."""
    result = await arkos_nodes.reflect_node({"document_draft": None})
    assert result == {"document_draft": None}


# --------------------------------------------------------------------------
# ADR-0415: draft_node's generate_image tool-call dispatch. Previously
# untested anywhere in the repo - the shared helper these tests exercise
# (nodes.py:_resolve_image_generation_call) is used by both Tekos's and
# Arkos's graph shapes, but only Arkos's task declares the tool today.
# --------------------------------------------------------------------------


async def test_draft_node_dispatches_a_generate_image_tool_call() -> None:
    """draft_node's own model call may choose to call generate_image instead
    of drafting prose directly - when it does, the tool result must land in
    generated_images and the follow-up (tool-less) call's reply becomes the
    document_draft, per _resolve_image_generation_call (nodes.py)."""
    captured_tool_call = {}

    async def fake_draft_invoke(**kwargs):
        return (
            _FakeModelResult(
                "",
                tool_calls=[
                    {
                        "name": "generate_image",
                        "args": {"prompt": "an OpenShift Operator icon"},
                        "id": "call_1",
                    }
                ],
            ),
            ProviderCandidate(name="ai-gateway"),
        )

    async def fake_invoke_tool(**kwargs):
        captured_tool_call.update(kwargs)
        # Real shape returned by agent-runtime's invoke_tool (mcp_client.py
        # returns resp.json() unmodified) - MCP Gateway's own /invoke route
        # always wraps a tool's payload in this envelope
        # (components/mcp-gateway/app/main.py). A flat dict here would
        # silently hide the KeyError('data_base64') regression this
        # unwrapping fixed - live-cluster-confirmed 2026-08-23.
        return {
            "tool": "generate_image",
            "capability": "image.generation.create",
            "result": {"data_base64": "abc123", "mime_type": "image/png", "alt": "an OpenShift Operator icon"},
        }

    async def fake_followup_invoke(**kwargs):
        return _FakeModelResult("Here's the OpenShift Operator icon."), ProviderCandidate(name="ai-gateway")

    saved_draft_invoke = arkos_nodes._model_router.invoke_with_fallback
    saved_invoke_tool = nodes.invoke_tool
    saved_followup_invoke = nodes._model_router.invoke_with_fallback
    try:
        arkos_nodes._model_router.invoke_with_fallback = fake_draft_invoke
        nodes.invoke_tool = fake_invoke_tool
        nodes._model_router.invoke_with_fallback = fake_followup_invoke
        state = {
            "message": "generate an image of the openshift operator",
            "bearer_token": "t",
            "request_id": "req-1",
        }
        result = await arkos_nodes.draft_node(state)
    finally:
        arkos_nodes._model_router.invoke_with_fallback = saved_draft_invoke
        nodes.invoke_tool = saved_invoke_tool
        nodes._model_router.invoke_with_fallback = saved_followup_invoke

    assert captured_tool_call.get("tool_name") == "generate_image"
    assert result["document_draft"] == "Here's the OpenShift Operator icon."
    assert result["generated_images"] == [
        {"data_base64": "abc123", "mime_type": "image/png", "alt": "an OpenShift Operator icon"}
    ]


async def test_draft_node_then_reflect_node_survives_an_empty_image_caption() -> None:
    """Regression test for the reported crash: a real user asked Arkos to
    generate an image, the model called generate_image, and the follow-up
    (tool-less) call composing the natural-language reply came back with
    empty content - a real, observed failure mode for a model that just
    executed a tool call and has nothing more to say. That left
    document_draft falsy, and reflect_node's old `if not draft: return {}`
    then violated LangGraph's "a node must write to at least one state key"
    contract on the very next node, surfacing as
    "Must write to at least one of [...]" in the chat reply."""

    async def fake_draft_invoke(**kwargs):
        return (
            _FakeModelResult(
                "",
                tool_calls=[
                    {
                        "name": "generate_image",
                        "args": {"prompt": "an OpenShift Operator icon"},
                        "id": "call_1",
                    }
                ],
            ),
            ProviderCandidate(name="ai-gateway"),
        )

    async def fake_invoke_tool(**kwargs):
        # Real envelope shape - see the other fake_invoke_tool above for
        # why a flat dict here would hide the real bug.
        return {
            "tool": "generate_image",
            "capability": "image.generation.create",
            "result": {"data_base64": "abc123", "mime_type": "image/png", "alt": "an OpenShift Operator icon"},
        }

    async def fake_followup_invoke(**kwargs):
        return _FakeModelResult(""), ProviderCandidate(name="ai-gateway")

    saved_draft_invoke = arkos_nodes._model_router.invoke_with_fallback
    saved_invoke_tool = nodes.invoke_tool
    saved_followup_invoke = nodes._model_router.invoke_with_fallback
    try:
        arkos_nodes._model_router.invoke_with_fallback = fake_draft_invoke
        nodes.invoke_tool = fake_invoke_tool
        nodes._model_router.invoke_with_fallback = fake_followup_invoke
        state = {
            "message": "can you generate an image of the openshift operator",
            "bearer_token": "t",
            "request_id": "req-1",
        }
        draft_result = await arkos_nodes.draft_node(state)
    finally:
        arkos_nodes._model_router.invoke_with_fallback = saved_draft_invoke
        nodes.invoke_tool = saved_invoke_tool
        nodes._model_router.invoke_with_fallback = saved_followup_invoke

    assert draft_result["document_draft"] == ""

    reflect_result = await arkos_nodes.reflect_node({**state, "document_draft": draft_result["document_draft"]})
    assert reflect_result == {"document_draft": ""}


async def test_draft_node_handles_a_downstream_error_nested_inside_the_mcp_envelope() -> None:
    """MCP Gateway returns HTTP 200 with the tool's own reported failure
    nested under "result" (e.g. image_gen.py's {"error": "..."} when
    OVHcloud itself errors) - this is a distinct case from invoke_tool
    raising McpClientError (an HTTP-level failure, e.g. a 503), which
    nodes.py's own except block already turns into a flat {"error": ...}
    with no "result" key. Before the 2026-08-23 envelope-unwrap fix, this
    nested-error shape was invisible to the old `"error" in tool_result`
    check (top-level tool_result never had an "error" key here) and would
    have been wrongly treated as success, crashing on a missing
    "data_base64" exactly like the KeyError regression this whole file's
    other generate_image tests exist to catch."""

    async def fake_draft_invoke(**kwargs):
        return (
            _FakeModelResult(
                "",
                tool_calls=[
                    {
                        "name": "generate_image",
                        "args": {"prompt": "an OpenShift Operator icon"},
                        "id": "call_1",
                    }
                ],
            ),
            ProviderCandidate(name="ai-gateway"),
        )

    async def fake_invoke_tool(**kwargs):
        return {
            "tool": "generate_image",
            "capability": "image.generation.create",
            "result": {"error": "image generation failed: Server error '503 Service Unavailable' for url '...'"},
        }

    async def fake_followup_invoke(**kwargs):
        return (
            _FakeModelResult("Sorry, I couldn't generate that image right now."),
            ProviderCandidate(name="ai-gateway"),
        )

    saved_draft_invoke = arkos_nodes._model_router.invoke_with_fallback
    saved_invoke_tool = nodes.invoke_tool
    saved_followup_invoke = nodes._model_router.invoke_with_fallback
    try:
        arkos_nodes._model_router.invoke_with_fallback = fake_draft_invoke
        nodes.invoke_tool = fake_invoke_tool
        nodes._model_router.invoke_with_fallback = fake_followup_invoke
        state = {
            "message": "can you generate an image of the openshift operator",
            "bearer_token": "t",
            "request_id": "req-1",
        }
        result = await arkos_nodes.draft_node(state)
    finally:
        arkos_nodes._model_router.invoke_with_fallback = saved_draft_invoke
        nodes.invoke_tool = saved_invoke_tool
        nodes._model_router.invoke_with_fallback = saved_followup_invoke

    assert result["document_draft"] == "Sorry, I couldn't generate that image right now."
    assert result.get("generated_images", []) == []


# --------------------------------------------------------------------------
# ADR-0121/WP-059: draft_node's git-forge tool-call dispatch. Regression
# coverage for the reported bug: git.* capabilities were declared in
# allowed_tools/tool-bindings.yaml/tool-policy.yaml since WP-059 but no node
# ever offered them to the model, so Arkos could never actually reach
# git-forge - live-cluster-confirmed 2026-08-23 (run_id
# 4848bb50-ea0c-495c-bff2-3219a38a5b89: zero git.* invocations ever across a
# real 3-hour production window). Shared helper under test:
# nodes.py:_resolve_git_forge_calls.
# --------------------------------------------------------------------------


async def test_draft_node_dispatches_a_single_list_repositories_tool_call() -> None:
    """The simple case: the model calls list_repositories once, gets a real
    result back, and the follow-up (tool-less) call's reply becomes the
    document_draft - same two-round shape as generate_image."""
    captured_tool_call = {}

    async def fake_draft_invoke(**kwargs):
        return (
            _FakeModelResult(
                "",
                tool_calls=[
                    {
                        "name": "list_repositories",
                        "args": {"provider": "github", "owner": "openshift", "owner_type": "organization"},
                        "id": "call_1",
                    }
                ],
            ),
            ProviderCandidate(name="ai-gateway"),
        )

    async def fake_invoke_tool(**kwargs):
        captured_tool_call.update(kwargs)
        return {
            "tool": "list_repositories",
            "capability": "git.repository.list",
            "result": {"owner": "openshift", "owner_type": "organization", "repositories": [{"name": "a"}, {"name": "b"}], "count": 2},
        }

    async def fake_followup_invoke(**kwargs):
        return _FakeModelResult("The openshift org has 2 public repositories."), ProviderCandidate(name="ai-gateway")

    saved_draft_invoke = arkos_nodes._model_router.invoke_with_fallback
    saved_invoke_tool = nodes.invoke_tool
    saved_followup_invoke = nodes._model_router.invoke_with_fallback
    try:
        arkos_nodes._model_router.invoke_with_fallback = fake_draft_invoke
        nodes.invoke_tool = fake_invoke_tool
        nodes._model_router.invoke_with_fallback = fake_followup_invoke
        state = {
            "message": "how many public repos does the openshift github org have?",
            "bearer_token": "t",
            "request_id": "req-1",
        }
        result = await arkos_nodes.draft_node(state)
    finally:
        arkos_nodes._model_router.invoke_with_fallback = saved_draft_invoke
        nodes.invoke_tool = saved_invoke_tool
        nodes._model_router.invoke_with_fallback = saved_followup_invoke

    # invoke_tool must be called with the platform capability ID, never the
    # provider tool name (tool-bindings.yaml's provider_tool field does that
    # translation server-side, not this node).
    assert captured_tool_call.get("tool_name") == "git.repository.list"
    assert result["document_draft"] == "The openshift org has 2 public repositories."
    # Arkos's own ambient classification is C3 (ADR-0415's comment on
    # image_generation_enabled) - _escalate(C3, C2) stays C3, it never
    # downgrades.
    assert result["effective_classification"] == "C3"


async def test_draft_node_dispatches_parallel_list_and_private_list_calls() -> None:
    """A provider with parallel tool-calling may return both
    list_repositories and list_private_repositories in the same completion
    (the reported "how many repos are public and private" case) - both must
    be resolved before the follow-up call, not just the first."""
    invoked_tool_names = []

    async def fake_draft_invoke(**kwargs):
        return (
            _FakeModelResult(
                "",
                tool_calls=[
                    {
                        "name": "list_repositories",
                        "args": {"provider": "gitlab", "owner": "zuno", "owner_type": "group"},
                        "id": "call_1",
                    },
                    {
                        "name": "list_private_repositories",
                        "args": {"provider": "gitlab", "owner": "zuno", "owner_type": "group"},
                        "id": "call_2",
                    },
                ],
            ),
            ProviderCandidate(name="ai-gateway"),
        )

    async def fake_invoke_tool(**kwargs):
        invoked_tool_names.append(kwargs.get("tool_name"))
        count = 3 if kwargs.get("tool_name") == "git.repository.list" else 7
        return {"result": {"owner": "zuno", "repositories": [], "count": count}}

    async def fake_followup_invoke(**kwargs):
        return _FakeModelResult("zuno has 3 public and 7 total repos."), ProviderCandidate(name="ai-gateway")

    saved_draft_invoke = arkos_nodes._model_router.invoke_with_fallback
    saved_invoke_tool = nodes.invoke_tool
    saved_followup_invoke = nodes._model_router.invoke_with_fallback
    try:
        arkos_nodes._model_router.invoke_with_fallback = fake_draft_invoke
        nodes.invoke_tool = fake_invoke_tool
        nodes._model_router.invoke_with_fallback = fake_followup_invoke
        state = {
            "message": "how many git repo are public and private for the zuno gitlab group?",
            "bearer_token": "t",
            "request_id": "req-1",
        }
        result = await arkos_nodes.draft_node(state)
    finally:
        arkos_nodes._model_router.invoke_with_fallback = saved_draft_invoke
        nodes.invoke_tool = saved_invoke_tool
        nodes._model_router.invoke_with_fallback = saved_followup_invoke

    assert set(invoked_tool_names) == {"git.repository.list", "git.repository.private.list"}
    assert result["document_draft"] == "zuno has 3 public and 7 total repos."


async def test_draft_node_resolves_a_second_sequential_git_round_then_forces_synthesis() -> None:
    """A provider WITHOUT parallel tool-calling (e.g. local vLLM) may return
    the two calls sequentially across completions instead of together: round
    1 returns list_repositories, the round-2 follow-up (still offered
    tools=) returns list_private_repositories instead of a final answer, and
    only round 3 (tools=None, forced) produces the final reply. A
    single-shot resolver would have silently dropped the second call - this
    is exactly the gap the 2-round cap exists to cover."""
    round_2_call_count = 0

    async def fake_draft_invoke(**kwargs):
        return (
            _FakeModelResult(
                "",
                tool_calls=[
                    {
                        "name": "list_repositories",
                        "args": {"provider": "gitlab", "owner": "zuno", "owner_type": "group"},
                        "id": "call_1",
                    }
                ],
            ),
            ProviderCandidate(name="ai-gateway"),
        )

    async def fake_invoke_tool(**kwargs):
        return {"result": {"owner": "zuno", "repositories": [], "count": 3}}

    async def fake_followup_invoke(**kwargs):
        nonlocal round_2_call_count
        round_2_call_count += 1
        if round_2_call_count == 1:
            assert kwargs.get("tools"), "round 2 must still offer the git tools"
            return (
                _FakeModelResult(
                    "",
                    tool_calls=[
                        {
                            "name": "list_private_repositories",
                            "args": {"provider": "gitlab", "owner": "zuno", "owner_type": "group"},
                            "id": "call_2",
                        }
                    ],
                ),
                ProviderCandidate(name="ai-gateway"),
            )
        assert kwargs.get("tools") is None, "round 3 must be a forced, tool-less synthesis call"
        return _FakeModelResult("zuno has 3 public and 7 total repos."), ProviderCandidate(name="ai-gateway")

    saved_draft_invoke = arkos_nodes._model_router.invoke_with_fallback
    saved_invoke_tool = nodes.invoke_tool
    saved_followup_invoke = nodes._model_router.invoke_with_fallback
    try:
        arkos_nodes._model_router.invoke_with_fallback = fake_draft_invoke
        nodes.invoke_tool = fake_invoke_tool
        nodes._model_router.invoke_with_fallback = fake_followup_invoke
        state = {
            "message": "how many git repo are public and private for the zuno gitlab group?",
            "bearer_token": "t",
            "request_id": "req-1",
        }
        result = await arkos_nodes.draft_node(state)
    finally:
        arkos_nodes._model_router.invoke_with_fallback = saved_draft_invoke
        nodes.invoke_tool = saved_invoke_tool
        nodes._model_router.invoke_with_fallback = saved_followup_invoke

    assert round_2_call_count == 2
    assert result["document_draft"] == "zuno has 3 public and 7 total repos."


def test_arkos_declares_the_confluence_capabilities_from_its_task() -> None:
    """Sanity check against the real checked-in bundle - confirms the
    module-level singletons resolved the actual draft-architecture-
    testimonial task, not a stale/empty one. drive.document.* is
    deliberately NOT asserted here - no google-workspace MCP server is
    deployed in this cluster, so the task's own file removed it from
    allowed_tools (write_node's McpClientError fallback still returns
    the draft as the reply either way)."""
    assert "confluence.page.search" in arkos_nodes._DRAFT_TASK.allowed_tools
    assert "drive.document.create" not in arkos_nodes._DRAFT_TASK.allowed_tools
    assert "knowledge.tech" in arkos_nodes._DRAFT_TASK.allowed_knowledge
    assert "knowledge.project" in arkos_nodes._DRAFT_TASK.allowed_knowledge


def test_reflect_slot_resolves_from_the_real_bundle() -> None:
    """ADR-0419 sanity check: the declarative reflect_node config actually
    came from agents/arkos/tasks/draft-architecture-testimonial.md's
    zuno.prompts.reflect and prompts/draft-architecture-testimonial--
    reflect.md, not the module's own hardcoded-literal safety net."""
    slot = arkos_nodes._DRAFT_TASK.prompts.get("reflect")
    assert slot is not None
    assert slot.classification_ceiling == "C2"
    assert slot.prompt and "reviewing your own draft" in slot.prompt
    assert arkos_nodes._REFLECT_CLASSIFICATION_CEILING == "C2"
    assert arkos_nodes._REFLECT_SYSTEM_PROMPT == slot.prompt


# --------------------------------------------------------------------------
# ADR-0514: workshop-presentation as a second kind through the same shape
# --------------------------------------------------------------------------


def test_arkos_declares_the_workshop_presentation_task() -> None:
    """Sanity check against the real checked-in bundle - confirms the
    module-level singleton resolved the actual workshop-presentation task
    and its prompt file."""
    assert arkos_nodes._WORKSHOP_TASK.name == "workshop-presentation"
    assert "confluence.page.search" in arkos_nodes._WORKSHOP_TASK.allowed_tools
    assert "drive.document.create" not in arkos_nodes._WORKSHOP_TASK.allowed_tools
    assert "knowledge.tech" in arkos_nodes._WORKSHOP_TASK.allowed_knowledge


def test_workshop_reflect_slot_resolves_from_the_real_bundle() -> None:
    """Same ADR-0419 sanity check as test_reflect_slot_resolves_from_the_
    real_bundle, for the second slot _resolve_reflect_slot now serves."""
    slot = arkos_nodes._WORKSHOP_TASK.prompts.get("reflect")
    assert slot is not None
    assert slot.classification_ceiling == "C2"
    assert slot.prompt and "reviewing your own draft" in slot.prompt
    assert arkos_nodes._WORKSHOP_REFLECT_CLASSIFICATION_CEILING == "C2"
    assert arkos_nodes._WORKSHOP_REFLECT_SYSTEM_PROMPT == slot.prompt


def test_classify_doc_kind_detects_workshop_and_odyssey_keywords() -> None:
    assert arkos_nodes._classify_doc_kind("Prepare a workshop for the Keycloak SSO migration") == "workshop"
    assert arkos_nodes._classify_doc_kind("Structure an Odyssey workshop about GPU sizing") == "workshop"
    assert arkos_nodes._classify_doc_kind("Draft a DAT for the OpenShift AI GPU sizing project") == "dat"


async def test_plan_node_classifies_a_workshop_request() -> None:
    result = await arkos_nodes.plan_node(
        {"message": "Prepare an Odyssey workshop for the Keycloak SSO migration"}
    )
    assert result["doc_plan"]["kind"] == "workshop"
    assert result["doc_plan"]["doc_title"].startswith("Workshop - ")


async def test_plan_node_defaults_to_dat_kind() -> None:
    result = await arkos_nodes.plan_node({"message": "Draft a DAT for the OpenShift AI GPU sizing project"})
    assert result["doc_plan"]["kind"] == "dat"
    assert result["doc_plan"]["doc_title"].startswith("DAT - ")


def test_active_task_resolves_workshop_vs_dat_from_doc_plan_kind() -> None:
    assert arkos_nodes._active_task({"doc_plan": {"kind": "workshop"}}) is arkos_nodes._WORKSHOP_TASK
    assert arkos_nodes._active_task({"doc_plan": {"kind": "dat"}}) is arkos_nodes._DRAFT_TASK
    assert arkos_nodes._active_task({}) is arkos_nodes._DRAFT_TASK


async def test_reflect_node_uses_the_workshop_slot_when_doc_plan_kind_is_workshop() -> None:
    """Same shape as test_reflect_node_uses_a_fixed_c2_ceiling_..., proving
    reflect_node picks the workshop task/slot instead of the DAT one when
    plan_node classified this turn as a workshop request."""
    captured = {}

    async def fake_invoke(**kwargs):
        captured.update(kwargs)
        return _FakeModelResult("a refined workshop draft"), ProviderCandidate(name="ai-gateway")

    saved_invoke = arkos_nodes._model_router.invoke_with_fallback
    try:
        arkos_nodes._model_router.invoke_with_fallback = fake_invoke
        state = {
            "document_draft": "the original workshop draft",
            "doc_plan": {"kind": "workshop"},
            "effective_classification": "C3",
            "local_only_required": False,
            "bearer_token": "t",
            "request_id": "req-1",
        }
        result = await arkos_nodes.reflect_node(state)
    finally:
        arkos_nodes._model_router.invoke_with_fallback = saved_invoke

    assert captured["classification"] == "C2"
    assert captured["task_name"] == "workshop-presentation"
    assert result["document_draft"] == "a refined workshop draft"


# --------------------------------------------------------------------------
# ADR-0417: coding-request early exit (route_after_plan / code_node)
# --------------------------------------------------------------------------


def test_arkos_declares_the_write_code_task() -> None:
    """Sanity check against the real checked-in bundle - confirms the
    module-level singleton resolved the actual write-code task."""
    assert arkos_nodes._WRITE_CODE_TASK.name == "write-code"


def test_route_after_plan_detects_a_coding_request() -> None:
    assert arkos_nodes.route_after_plan({"message": "write me a Terraform snippet for this workshop"}) == "code"


def test_route_after_plan_falls_through_to_retrieve_for_a_dat_request() -> None:
    assert (
        arkos_nodes.route_after_plan({"message": "draft a DAT for the OpenShift AI GPU sizing project"})
        == "retrieve"
    )


async def test_code_node_uses_a_fixed_c2_ceiling_and_the_write_code_task_name() -> None:
    captured = {}

    async def fake_invoke(**kwargs):
        captured.update(kwargs)
        return _FakeModelResult("```hcl\nresource \"x\" {}\n```"), ProviderCandidate(name="ai-gateway")

    saved_invoke = arkos_nodes._model_router.invoke_with_fallback
    try:
        arkos_nodes._model_router.invoke_with_fallback = fake_invoke
        state = {
            "message": "write me a Terraform snippet",
            "bearer_token": "t",
            "request_id": "req-1",
            "local_only_required": False,
        }
        result = await arkos_nodes.code_node(state)
    finally:
        arkos_nodes._model_router.invoke_with_fallback = saved_invoke

    assert captured["classification"] == "C2", "must not inherit Arkos's ambient C3 seed"
    assert captured["task_name"] == "write-code"
    assert captured["agent_name"] == "arkos"
    assert result["citations"] == []
    assert result["source_mode"] == "none"
    assert result["provider_used"] == "ai-gateway"


async def test_code_node_provider_failure_is_a_visible_error_not_a_silent_fallback() -> None:
    """The (arkos, write-code) preference is strict: true - Codestral only,
    no local/SaaS substitute. A ModelRouterError here must surface as a
    visible failure reply, never a silently different provider's answer."""

    async def failing_invoke(**kwargs):
        raise ModelRouterError("all eligible providers failed")

    saved_invoke = arkos_nodes._model_router.invoke_with_fallback
    try:
        arkos_nodes._model_router.invoke_with_fallback = failing_invoke
        result = await arkos_nodes.code_node({"message": "write a bash script", "bearer_token": "t", "request_id": "r"})
    finally:
        arkos_nodes._model_router.invoke_with_fallback = saved_invoke

    assert "try again" in result["reply"].lower()
    assert result["provider_used"] is None
    assert result["citations"] == []
    assert result["source_mode"] == "none"


# --------------------------------------------------------------------------
# structure-demo: demo-narrative early exit (route_after_plan / demo_node)
# --------------------------------------------------------------------------


def test_arkos_declares_the_structure_demo_task() -> None:
    """Sanity check against the real checked-in bundle - confirms the
    module-level singleton resolved the actual structure-demo task and
    its prompt file (unlike write-code, this task's prompt lives in
    Markdown, not a Python literal - see the module's own comment)."""
    assert arkos_nodes._STRUCTURE_DEMO_TASK.name == "structure-demo"
    assert arkos_nodes._STRUCTURE_DEMO_TASK.prompt
    assert "demo narrative" in arkos_nodes._STRUCTURE_DEMO_TASK.prompt.lower()


def test_route_after_plan_detects_a_demo_request() -> None:
    assert (
        arkos_nodes.route_after_plan({"message": "Structure a demo for the OpenShift AI GPU sizing project"})
        == "demo"
    )


def test_route_after_plan_prefers_code_over_demo_when_both_could_match() -> None:
    """A coding request checked first, same order code_node/demo_node are
    declared in plan_draft_write.py's conditional edges."""
    assert (
        arkos_nodes.route_after_plan({"message": "write me a Terraform snippet for this workshop"}) == "code"
    )


async def test_demo_node_uses_arkos_ambient_classification_and_the_structure_demo_task_name() -> None:
    captured = {}

    async def fake_invoke(**kwargs):
        captured.update(kwargs)
        return _FakeModelResult("1. Opening...\n2. Show the RAG pipeline..."), ProviderCandidate(name="ai-gateway")

    saved_invoke = arkos_nodes._model_router.invoke_with_fallback
    try:
        arkos_nodes._model_router.invoke_with_fallback = fake_invoke
        state = {
            "message": "Structure a demo for the OpenShift AI GPU sizing project",
            "bearer_token": "t",
            "request_id": "req-1",
            "local_only_required": False,
        }
        result = await arkos_nodes.demo_node(state)
    finally:
        arkos_nodes._model_router.invoke_with_fallback = saved_invoke

    assert captured["classification"] == arkos_nodes.ARKOS_BASE_CLASSIFICATION
    assert captured["task_name"] == "structure-demo"
    assert captured["agent_name"] == "arkos"
    assert result["citations"] == []
    assert result["source_mode"] == "none"
    assert result["provider_used"] == "ai-gateway"


async def test_demo_node_provider_failure_is_a_visible_error() -> None:
    async def failing_invoke(**kwargs):
        raise ModelRouterError("all eligible providers failed")

    saved_invoke = arkos_nodes._model_router.invoke_with_fallback
    try:
        arkos_nodes._model_router.invoke_with_fallback = failing_invoke
        result = await arkos_nodes.demo_node(
            {"message": "structure a demo", "bearer_token": "t", "request_id": "r"}
        )
    finally:
        arkos_nodes._model_router.invoke_with_fallback = saved_invoke

    assert "try again" in result["reply"].lower()
    assert result["provider_used"] is None
    assert result["citations"] == []
    assert result["source_mode"] == "none"


TESTS = [
    test_extract_topic_from_a_dat_request,
    test_extract_topic_accepts_the_full_phrase_too,
    test_extract_topic_falls_back_to_the_whole_message_when_unmatched,
    test_source_mode_indexed_only,
    test_source_mode_live_only,
    test_source_mode_both,
    test_source_mode_none_when_nothing_contributed,
    test_source_mode_ignores_an_empty_confluence_result_as_not_live,
    test_citations_include_both_rag_docs_and_confluence_results,
    test_drive_result_url_unwraps_the_gateway_result_envelope,
    test_drive_result_url_falls_back_to_a_flat_shape,
    test_drive_result_url_is_none_when_absent,
    test_reflect_node_uses_a_fixed_c2_ceiling_regardless_of_effective_classification,
    test_reflect_node_still_honors_local_only_required,
    test_reflect_node_is_a_noop_without_a_draft,
    test_draft_node_dispatches_a_generate_image_tool_call,
    test_draft_node_then_reflect_node_survives_an_empty_image_caption,
    test_draft_node_dispatches_a_single_list_repositories_tool_call,
    test_draft_node_dispatches_parallel_list_and_private_list_calls,
    test_draft_node_resolves_a_second_sequential_git_round_then_forces_synthesis,
    test_arkos_declares_the_confluence_capabilities_from_its_task,
    test_reflect_slot_resolves_from_the_real_bundle,
    test_arkos_declares_the_workshop_presentation_task,
    test_workshop_reflect_slot_resolves_from_the_real_bundle,
    test_classify_doc_kind_detects_workshop_and_odyssey_keywords,
    test_plan_node_classifies_a_workshop_request,
    test_plan_node_defaults_to_dat_kind,
    test_active_task_resolves_workshop_vs_dat_from_doc_plan_kind,
    test_reflect_node_uses_the_workshop_slot_when_doc_plan_kind_is_workshop,
    test_arkos_declares_the_write_code_task,
    test_route_after_plan_detects_a_coding_request,
    test_route_after_plan_falls_through_to_retrieve_for_a_dat_request,
    test_code_node_uses_a_fixed_c2_ceiling_and_the_write_code_task_name,
    test_code_node_provider_failure_is_a_visible_error_not_a_silent_fallback,
    test_arkos_declares_the_structure_demo_task,
    test_route_after_plan_detects_a_demo_request,
    test_route_after_plan_prefers_code_over_demo_when_both_could_match,
    test_demo_node_uses_arkos_ambient_classification_and_the_structure_demo_task_name,
    test_demo_node_provider_failure_is_a_visible_error,
]


async def _run_all() -> int:
    failed = 0
    for test in TESTS:
        try:
            result = test()
            if asyncio.iscoroutine(result):
                await result
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    return failed


def main() -> int:
    failed = asyncio.run(_run_all())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
