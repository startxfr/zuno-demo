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
from app.graph import arkos_nodes  # noqa: E402


class _FakeModelResult:
    def __init__(self, content: str) -> None:
        self.content = content


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
    result = await arkos_nodes.reflect_node({"document_draft": None})
    assert result == {}


def test_arkos_declares_the_confluence_and_drive_capabilities_from_its_task() -> None:
    """Sanity check against the real checked-in bundle - confirms the
    module-level singletons resolved the actual draft-architecture-
    testimonial task, not a stale/empty one."""
    assert "confluence.page.search" in arkos_nodes._DRAFT_TASK.allowed_tools
    assert "drive.document.create" in arkos_nodes._DRAFT_TASK.allowed_tools
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
    test_arkos_declares_the_confluence_and_drive_capabilities_from_its_task,
    test_reflect_slot_resolves_from_the_real_bundle,
    test_arkos_declares_the_write_code_task,
    test_route_after_plan_detects_a_coding_request,
    test_route_after_plan_falls_through_to_retrieve_for_a_dat_request,
    test_code_node_uses_a_fixed_c2_ceiling_and_the_write_code_task_name,
    test_code_node_provider_failure_is_a_visible_error_not_a_silent_fallback,
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
