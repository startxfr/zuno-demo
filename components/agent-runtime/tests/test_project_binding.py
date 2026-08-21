#!/usr/bin/env python3
"""ADR-0512/WP-55 tests: app/project_binding.py's verification/matching
logic, app/main.py's pre-graph binding wiring (_bind_project_if_required),
and app/graph/nodes.py's quota-header gating (project_id only reaches
ai-gateway for a task that actually declared project_required).

Same no-pytest, no-live-cluster, run-directly convention as
tests/test_project_memory_e2e.py/test_conversations.py: no live MCP
Gateway/Salesforce, no live conversations Postgres. mcp_client.invoke_tool
and conversations.get_project_binding are monkeypatched at their module
boundary (the same pattern test_project_memory_e2e.py uses for
project_memory_client.write_project_memory) rather than faking an HTTP
server or a psycopg pool - this repo has no existing precedent for
mocking the conversations SQL round trip itself (test_conversations.py
only proves the None-pool/PoolTimeout degrade paths), so this suite
follows that same boundary rather than inventing new test infrastructure
for it.

Run directly:

    cd components/agent-runtime && python3 tests/test_project_binding.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))
os.environ.setdefault(
    "KNOWLEDGE_POLICY_PATH", str(_REPO_ROOT / "policies" / "knowledge" / "knowledge-policy.yaml")
)
os.environ.setdefault("QUOTA_POLICY_PATH", str(_REPO_ROOT / "policies" / "quotas" / "quota-policy.yaml"))

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

import app.conversations as conversations_module  # noqa: E402
import app.project_binding as project_binding  # noqa: E402
from app.auth import CallerIdentity  # noqa: E402
from app.clients import mcp_client  # noqa: E402
from app.graph import nodes  # noqa: E402
from app.graph.nodes import _make_reason_node, _registry  # noqa: E402
from app.main import _bind_project_if_required  # noqa: E402
from app.registry import AgentDefinition, TaskDefinition  # noqa: E402
from app.schemas import ChatRequest  # noqa: E402

# project_binding.py loaded policies/quotas/quota-policy.yaml's
# project_binding.validity_window at import time (module-scope constant,
# same pattern as ai-gateway's own budget loading) - reused directly here
# rather than re-parsing "24h" ourselves, so this suite can never silently
# drift from whatever the policy file actually says.
assert project_binding.VALIDITY_WINDOW_SECONDS > 0, (
    "policies/quotas/quota-policy.yaml's project_binding.validity_window failed to load - "
    "every test below that depends on cache-freshness would be meaningless against a 0 window"
)


def _identity(sub: str = "alice", groups=None) -> CallerIdentity:
    return CallerIdentity(sub=sub, groups=groups or ["finance"], raw_claims={}, token="fake-token")


# --------------------------------------------------------------------------
# Pure logic: _select_match / _looks_like_salesforce_id / window parsing
# --------------------------------------------------------------------------

_ID_RESULTS = [
    {"id": "006AbCdEfGhIjKlMno", "title": "Acme Renewal FY26"},
    {"id": "006ZzYxWvUtSrQpOnM", "title": "Acme Expansion FY26"},
]


def test_looks_like_salesforce_id_matches_standard_prefix_and_length() -> None:
    assert project_binding._looks_like_salesforce_id("006AbCdEfGhIjKlMno")
    assert not project_binding._looks_like_salesforce_id("Acme Renewal FY26")
    assert not project_binding._looks_like_salesforce_id("006tooshort")


def test_select_match_requires_exact_id_for_id_shaped_candidate() -> None:
    assert project_binding._select_match("006AbCdEfGhIjKlMno", _ID_RESULTS) == "006AbCdEfGhIjKlMno"
    # An id-shaped candidate that isn't literally one of the returned ids
    # is unknown, even if results is non-empty - never falls back to a
    # name-style match for something that already looks like an id.
    assert project_binding._select_match("006NoSuchOpportunity", _ID_RESULTS) is None


def test_select_match_accepts_exact_title_case_insensitive() -> None:
    results = [{"id": "006A", "title": "Acme Renewal FY26"}, {"id": "006B", "title": "Acme Expansion FY26"}]
    assert project_binding._select_match("acme renewal fy26", results) == "006A"


def test_select_match_accepts_sole_unambiguous_result_for_name_candidate() -> None:
    results = [{"id": "006A", "title": "Acme Corp - Renewal"}]
    assert project_binding._select_match("Acme", results) == "006A"


def test_select_match_returns_none_for_zero_or_ambiguous_matches() -> None:
    assert project_binding._select_match("Nothing Matches This", []) is None
    # Two results, neither an exact title match -> ambiguous, folds into
    # unknown_project rather than picking one arbitrarily.
    ambiguous = [{"id": "006A", "title": "Acme Renewal FY26"}, {"id": "006B", "title": "Acme Expansion FY26"}]
    assert project_binding._select_match("Acme", ambiguous) is None


def test_window_seconds_parses_each_unit() -> None:
    assert project_binding._window_seconds("30s") == 30
    assert project_binding._window_seconds("5m") == 300
    assert project_binding._window_seconds("24h") == 86400
    assert project_binding._window_seconds("2d") == 172800


def test_is_binding_still_valid_true_within_window_false_past_it_and_on_none() -> None:
    assert project_binding.is_binding_still_valid(None) is False
    fresh = datetime.now(timezone.utc) - timedelta(seconds=5)
    assert project_binding.is_binding_still_valid(fresh) is True
    stale = datetime.now(timezone.utc) - timedelta(seconds=project_binding.VALIDITY_WINDOW_SECONDS + 60)
    assert project_binding.is_binding_still_valid(stale) is False


# --------------------------------------------------------------------------
# verify_project_binding - mcp_client.invoke_tool mocked
# --------------------------------------------------------------------------


async def test_verify_project_binding_raises_candidate_missing_when_blank() -> None:
    try:
        await project_binding.verify_project_binding(
            "  ", bearer_token="t", agent_name="finage", task_name="identify-business-ready-to-invoice"
        )
        raise AssertionError("expected ProjectCandidateMissingError")
    except project_binding.ProjectCandidateMissingError:
        pass


async def test_verify_project_binding_succeeds_on_id_match() -> None:
    async def fake_invoke_tool_real(tool_name, arguments, **kwargs):
        assert tool_name == "salesforce.opportunity.read"
        assert arguments == {"query": "006AbCdEfGhIjKlMno", "limit": 5}
        assert kwargs["bearer_token"] == "t"
        assert kwargs["data_classification"] == "C2"
        return {"query": "006AbCdEfGhIjKlMno", "results": _ID_RESULTS, "count": 2}

    saved = mcp_client.invoke_tool
    mcp_client.invoke_tool = fake_invoke_tool_real
    try:
        result = await project_binding.verify_project_binding(
            "006AbCdEfGhIjKlMno", bearer_token="t", agent_name="finage", task_name="identify-business-ready-to-invoice"
        )
        assert result == "006AbCdEfGhIjKlMno"
    finally:
        mcp_client.invoke_tool = saved


async def test_verify_project_binding_raises_access_denied_on_403() -> None:
    async def fake_invoke_tool(tool_name, arguments, **kwargs):
        raise mcp_client.McpClientError("403 Forbidden", status_code=403)

    saved = mcp_client.invoke_tool
    mcp_client.invoke_tool = fake_invoke_tool
    try:
        try:
            await project_binding.verify_project_binding(
                "Acme", bearer_token="t", agent_name="finage", task_name="identify-business-ready-to-invoice"
            )
            raise AssertionError("expected ProjectAccessDeniedError")
        except project_binding.ProjectAccessDeniedError:
            pass
    finally:
        mcp_client.invoke_tool = saved


async def test_verify_project_binding_raises_unreachable_on_transport_error() -> None:
    async def fake_invoke_tool(tool_name, arguments, **kwargs):
        raise mcp_client.McpClientError("connection refused", status_code=None)

    saved = mcp_client.invoke_tool
    mcp_client.invoke_tool = fake_invoke_tool
    try:
        try:
            await project_binding.verify_project_binding(
                "Acme", bearer_token="t", agent_name="finage", task_name="identify-business-ready-to-invoice"
            )
            raise AssertionError("expected ProjectBindingUnreachableError")
        except project_binding.ProjectBindingUnreachableError:
            pass
    finally:
        mcp_client.invoke_tool = saved


async def test_verify_project_binding_raises_not_found_on_zero_matches() -> None:
    async def fake_invoke_tool(tool_name, arguments, **kwargs):
        return {"query": arguments["query"], "results": [], "count": 0}

    saved = mcp_client.invoke_tool
    mcp_client.invoke_tool = fake_invoke_tool
    try:
        try:
            await project_binding.verify_project_binding(
                "Nonexistent Deal", bearer_token="t", agent_name="finage", task_name="identify-business-ready-to-invoice"
            )
            raise AssertionError("expected ProjectNotFoundError")
        except project_binding.ProjectNotFoundError:
            pass
    finally:
        mcp_client.invoke_tool = saved


# --------------------------------------------------------------------------
# app/main.py's _bind_project_if_required wiring
# --------------------------------------------------------------------------


def _fake_agent(task: TaskDefinition, primary_task_name: str = "t") -> AgentDefinition:
    return AgentDefinition(
        name="fake-agent",
        status="active",
        preferred_classification="C2",
        rag_top_k=5,
        tasks={primary_task_name: task},
        primary_task=primary_task_name,
    )


async def test_bind_project_if_required_returns_none_for_unmarked_task() -> None:
    """Unmarked tasks must be byte-identical to pre-ADR-0512 behavior: zero
    calls into conversations.get_project_binding or project_binding at
    all - proven here by never monkeypatching either and still getting a
    clean None back."""
    task = TaskDefinition(name="t", title="T", description="", allowed_tools=[], project_required=False)
    agent = _fake_agent(task)
    payload = ChatRequest(session_id="s", user_sub="alice", message="hi", project_id=None)
    result = await _bind_project_if_required(agent, payload, _identity(), conversations_pool=None, run_id="run-1")
    assert result is None


async def test_bind_project_if_required_uses_fresh_cached_binding_without_reverifying() -> None:
    task = TaskDefinition(name="t", title="T", description="", allowed_tools=["salesforce.opportunity.read"], project_required=True)
    agent = _fake_agent(task)
    payload = ChatRequest(session_id="s", user_sub="alice", message="hi", project_id=None)

    fresh = datetime.now(timezone.utc) - timedelta(seconds=5)

    async def fake_get_project_binding(pool, *, run_id):
        return {"project_id": "006CachedOpportunity", "project_id_verified_at": fresh}

    verify_calls = []

    async def fake_verify(*args, **kwargs):
        verify_calls.append((args, kwargs))
        raise AssertionError("should never re-verify within the validity window")

    saved_get = conversations_module.get_project_binding
    saved_verify = project_binding.verify_project_binding
    conversations_module.get_project_binding = fake_get_project_binding
    project_binding.verify_project_binding = fake_verify
    try:
        result = await _bind_project_if_required(
            agent, payload, _identity(), conversations_pool=object(), run_id="run-2"
        )
        assert result == "006CachedOpportunity"
        assert not verify_calls
    finally:
        conversations_module.get_project_binding = saved_get
        project_binding.verify_project_binding = saved_verify


async def test_bind_project_if_required_reverifies_past_the_validity_window() -> None:
    task = TaskDefinition(name="t", title="T", description="", allowed_tools=["salesforce.opportunity.read"], project_required=True)
    agent = _fake_agent(task)
    payload = ChatRequest(session_id="s", user_sub="alice", message="hi", project_id="Acme Renewal FY26")

    stale = datetime.now(timezone.utc) - timedelta(seconds=project_binding.VALIDITY_WINDOW_SECONDS + 60)

    async def fake_get_project_binding(pool, *, run_id):
        return {"project_id": "006Stale", "project_id_verified_at": stale}

    async def fake_verify(candidate, **kwargs):
        assert candidate == "Acme Renewal FY26"
        return "006FreshlyVerified"

    saved_get = conversations_module.get_project_binding
    saved_verify = project_binding.verify_project_binding
    conversations_module.get_project_binding = fake_get_project_binding
    project_binding.verify_project_binding = fake_verify
    try:
        result = await _bind_project_if_required(
            agent, payload, _identity(), conversations_pool=object(), run_id="run-3"
        )
        assert result == "006FreshlyVerified"
    finally:
        conversations_module.get_project_binding = saved_get
        project_binding.verify_project_binding = saved_verify


async def test_bind_project_if_required_maps_each_typed_error_to_the_right_http_status() -> None:
    task = TaskDefinition(name="t", title="T", description="", allowed_tools=["salesforce.opportunity.read"], project_required=True)
    agent = _fake_agent(task)

    async def fake_get_project_binding(pool, *, run_id):
        return None  # no cached binding - always falls through to verify

    saved_get = conversations_module.get_project_binding
    saved_verify = project_binding.verify_project_binding
    conversations_module.get_project_binding = fake_get_project_binding

    cases = [
        (project_binding.ProjectCandidateMissingError, 400),
        (project_binding.ProjectNotFoundError, 404),
        (project_binding.ProjectAccessDeniedError, 403),
        (project_binding.ProjectBindingUnreachableError, 503),
    ]
    try:
        for error_cls, expected_status in cases:
            async def fake_verify(*args, _cls=error_cls, **kwargs):
                raise _cls("boom")

            project_binding.verify_project_binding = fake_verify
            payload = ChatRequest(session_id="s", user_sub="alice", message="hi", project_id="whatever")
            try:
                await _bind_project_if_required(agent, payload, _identity(), conversations_pool=object(), run_id="run-4")
                raise AssertionError(f"expected HTTPException for {error_cls.__name__}")
            except Exception as exc:  # HTTPException
                assert getattr(exc, "status_code", None) == expected_status, (error_cls.__name__, exc)
    finally:
        conversations_module.get_project_binding = saved_get
        project_binding.verify_project_binding = saved_verify


async def test_bind_project_if_required_uses_finages_real_project_required_tasks() -> None:
    """Not a fixture - the REAL Finage bundle, parsed by the real registry
    (AGENTS_DIR set at the top of this file), proving
    identify-business-ready-to-invoice/monthly-invoice-report genuinely
    carry project_required: true end to end from the OKF Markdown file
    through app/registry.py's TaskDefinition, not just in a hand-built
    test fixture."""
    finage = _registry.get("finage")
    assert finage is not None, "finage bundle failed to load from AGENTS_DIR"
    invoice_task = finage.tasks["identify-business-ready-to-invoice"]
    assert invoice_task.project_required is True
    report_task = finage.tasks["monthly-invoice-report"]
    assert report_task.project_required is True
    # answer-finance-question (Finage's real primary_task) must stay
    # unmarked - this ADR must not silently widen to tasks it wasn't
    # asked to cover.
    assert finage.tasks["answer-finance-question"].project_required is False

    async def fake_get_project_binding(pool, *, run_id):
        return None

    async def fake_verify(candidate, **kwargs):
        assert candidate == "Acme Renewal FY26"
        assert kwargs["task_name"] == "identify-business-ready-to-invoice"
        return "006Verified"

    saved_get = conversations_module.get_project_binding
    saved_verify = project_binding.verify_project_binding
    conversations_module.get_project_binding = fake_get_project_binding
    project_binding.verify_project_binding = fake_verify
    try:
        agent_with_invoice_primary = _fake_agent(invoice_task, primary_task_name="identify-business-ready-to-invoice")
        payload = ChatRequest(session_id="s", user_sub="alice", message="hi", project_id="Acme Renewal FY26")
        result = await _bind_project_if_required(
            agent_with_invoice_primary, payload, _identity(), conversations_pool=object(), run_id="run-5"
        )
        assert result == "006Verified"
    finally:
        conversations_module.get_project_binding = saved_get
        project_binding.verify_project_binding = saved_verify


# --------------------------------------------------------------------------
# app/conversations.py - record_turn's new optional project_id param must
# not disturb the existing None-pool no-op contract.
# --------------------------------------------------------------------------


async def test_record_turn_with_project_id_still_no_ops_on_a_none_pool() -> None:
    await conversations_module.record_turn(
        None, run_id="run-abc", agent_name="finage", owner_sub="alice",
        opening_message="hi", project_id="006Verified",
    )  # no exception raised = pass


async def test_get_project_binding_fails_closed_on_a_none_pool() -> None:
    try:
        await conversations_module.get_project_binding(None, run_id="run-abc")
        raise AssertionError("expected HTTPException(503)")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 503


# --------------------------------------------------------------------------
# app/graph/nodes.py - quota-header gating (finding 4: only a task's own
# project_required mark may let state["project_id"] reach ai-gateway's
# X-Zuno-Project-Id header, never merely state["project_id"] being truthy)
# --------------------------------------------------------------------------


async def test_reason_node_forwards_project_id_only_when_task_is_project_required() -> None:
    prompt_task = TaskDefinition(
        name="t", title="T", description="", allowed_tools=[], prompt="You are a test agent.",
    )
    agent = AgentDefinition(name="fake-agent", status="active", preferred_classification="C2", rag_top_k=5)

    captured = []

    async def fake_invoke_with_fallback(**kwargs):
        captured.append(kwargs.get("project_id"))
        return SimpleNamespace(content="ok", tool_calls=[]), SimpleNamespace(name="ai-gateway")

    saved = nodes._model_router.invoke_with_fallback
    nodes._model_router.invoke_with_fallback = fake_invoke_with_fallback
    try:
        state = {
            "message": "hi", "bearer_token": "t", "request_id": "req-1",
            "project_id": "006ShouldOnlyLeakWhenRequired",
            "retrieved_docs": [], "tool_results": {}, "errors": [], "history": [], "summary": "",
        }
        # project_required False: header must stay unset even though
        # state["project_id"] is truthy - this is finding 4's actual fix.
        prompt_task.project_required = False
        reason_node = _make_reason_node(agent, prompt_task)
        await reason_node(state)
        assert captured[-1] is None, "an ordinary task must never leak project_id into the quota header"

        # project_required True: the same truthy state["project_id"] must
        # now reach invoke_with_fallback.
        prompt_task.project_required = True
        reason_node = _make_reason_node(agent, prompt_task)
        await reason_node(state)
        assert captured[-1] == "006ShouldOnlyLeakWhenRequired"
    finally:
        nodes._model_router.invoke_with_fallback = saved


TESTS = [
    test_looks_like_salesforce_id_matches_standard_prefix_and_length,
    test_select_match_requires_exact_id_for_id_shaped_candidate,
    test_select_match_accepts_exact_title_case_insensitive,
    test_select_match_accepts_sole_unambiguous_result_for_name_candidate,
    test_select_match_returns_none_for_zero_or_ambiguous_matches,
    test_window_seconds_parses_each_unit,
    test_is_binding_still_valid_true_within_window_false_past_it_and_on_none,
    test_verify_project_binding_raises_candidate_missing_when_blank,
    test_verify_project_binding_succeeds_on_id_match,
    test_verify_project_binding_raises_access_denied_on_403,
    test_verify_project_binding_raises_unreachable_on_transport_error,
    test_verify_project_binding_raises_not_found_on_zero_matches,
    test_bind_project_if_required_returns_none_for_unmarked_task,
    test_bind_project_if_required_uses_fresh_cached_binding_without_reverifying,
    test_bind_project_if_required_reverifies_past_the_validity_window,
    test_bind_project_if_required_maps_each_typed_error_to_the_right_http_status,
    test_bind_project_if_required_uses_finages_real_project_required_tasks,
    test_record_turn_with_project_id_still_no_ops_on_a_none_pool,
    test_get_project_binding_fails_closed_on_a_none_pool,
    test_reason_node_forwards_project_id_only_when_task_is_project_required,
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
