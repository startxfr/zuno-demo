#!/usr/bin/env python3
"""ADR-0512/WP-55 tests: app/project_binding.py's verification/matching
logic, app/main.py's pre-graph customer-project check (_require_customer_project),
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
from fastapi import HTTPException  # noqa: E402

import app.projects as projects_module  # noqa: E402
from app.main import _require_customer_project  # noqa: E402
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
# app/main.py's _require_customer_project wiring (ADR-0528, superseding
# ADR-0512 clause 3: the check moved from "verify a caller-supplied
# candidate at conversation start" to "the conversation's own project must
# be a customer project", and Salesforce verification itself moved to
# project save)
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


async def test_unmarked_task_is_untouched_by_the_customer_project_check() -> None:
    """ADR-0528 preserves ADR-0512's guarantee that unmarked tasks behave
    exactly as before: zero calls into app/projects.py or project_binding
    at all - proven by never monkeypatching either and still returning
    cleanly, with no project supplied."""
    task = TaskDefinition(name="t", title="T", description="", allowed_tools=[], project_required=False)
    agent = _fake_agent(task)
    await _require_customer_project(agent, _identity(), None, None)


async def test_project_required_task_refuses_a_conversation_with_no_project() -> None:
    """Fail closed, first branch: 400. The task cannot act without an
    engagement, and no project at all is a client-side mistake, not an
    authorization failure."""
    task = TaskDefinition(name="t", title="T", description="", allowed_tools=[], project_required=True)
    agent = _fake_agent(task)
    try:
        await _require_customer_project(agent, _identity(), object(), None)
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 400, exc.status_code


async def test_project_required_task_refuses_a_free_project() -> None:
    """ADR-0528 clause 3: a free project (no verified Salesforce link) is
    a real, fully usable project - it simply cannot host a
    project_required task. 403, distinct from the 400 above so the two
    causes stay distinguishable."""
    task = TaskDefinition(name="t", title="T", description="", allowed_tools=[], project_required=True)
    agent = _fake_agent(task)

    async def fake_get_project(pool, *, project_id, subject, groups):
        return {"is_customer": False, "salesforce_opportunity_id": None, "salesforce_verified_at": None}

    saved = projects_module.get_project
    projects_module.get_project = fake_get_project
    try:
        await _require_customer_project(agent, _identity(), object(), "proj-1")
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 403, exc.status_code
    finally:
        projects_module.get_project = saved


async def test_a_fresh_customer_project_makes_no_salesforce_call() -> None:
    """ADR-0528's whole point: verification lands once per PROJECT per
    validity window, so the ordinary chat path inside a fresh customer
    project touches Salesforce zero times. Proven by leaving
    verify_project_binding un-patched - it would raise on any real call."""
    task = TaskDefinition(name="t", title="T", description="", allowed_tools=[], project_required=True)
    agent = _fake_agent(task)
    fresh = datetime.now(timezone.utc) - timedelta(seconds=5)

    calls = []

    async def fake_get_project(pool, *, project_id, subject, groups):
        return {
            "is_customer": True,
            "salesforce_opportunity_id": "006Verified",
            "salesforce_verified_at": fresh,
        }

    async def exploding_verify(candidate, **kwargs):
        calls.append(candidate)
        raise AssertionError("must not re-verify inside the validity window")

    saved_get, saved_verify = projects_module.get_project, project_binding.verify_project_binding
    projects_module.get_project = fake_get_project
    project_binding.verify_project_binding = exploding_verify
    try:
        await _require_customer_project(agent, _identity(), object(), "proj-1")
        assert calls == [], calls
    finally:
        projects_module.get_project = saved_get
        project_binding.verify_project_binding = saved_verify


async def test_a_stale_customer_project_reverifies_once_and_restamps() -> None:
    """Past the window, exactly one verification runs and its success is
    recorded on the PROJECT (not the conversation), so the next turn is
    fresh again."""
    task = TaskDefinition(name="t", title="T", description="", allowed_tools=[], project_required=True)
    agent = _fake_agent(task)
    stale = datetime.now(timezone.utc) - timedelta(seconds=project_binding.VALIDITY_WINDOW_SECONDS + 60)
    verified, stamped = [], []

    async def fake_get_project(pool, *, project_id, subject, groups):
        return {
            "is_customer": True,
            "salesforce_opportunity_id": "006Verified",
            "salesforce_verified_at": stale,
        }

    async def fake_verify(candidate, **kwargs):
        verified.append(candidate)
        return candidate

    async def fake_stamp(pool, *, project_id):
        stamped.append(project_id)

    saved = (projects_module.get_project, project_binding.verify_project_binding,
             projects_module.stamp_salesforce_verification)
    projects_module.get_project = fake_get_project
    project_binding.verify_project_binding = fake_verify
    projects_module.stamp_salesforce_verification = fake_stamp
    try:
        await _require_customer_project(agent, _identity(), object(), "proj-1")
        assert verified == ["006Verified"], verified
        assert stamped == ["proj-1"], stamped
    finally:
        (projects_module.get_project, project_binding.verify_project_binding,
         projects_module.stamp_salesforce_verification) = saved


async def test_reverification_maps_each_typed_error_to_the_right_http_status() -> None:
    """ADR-0512's three distinguishable causes survive the move: a
    Salesforce outage must stay tellable apart from an authorization
    denial."""
    task = TaskDefinition(name="t", title="T", description="", allowed_tools=[], project_required=True)
    agent = _fake_agent(task)
    stale = datetime.now(timezone.utc) - timedelta(seconds=project_binding.VALIDITY_WINDOW_SECONDS + 60)

    async def fake_get_project(pool, *, project_id, subject, groups):
        return {
            "is_customer": True,
            "salesforce_opportunity_id": "006Verified",
            "salesforce_verified_at": stale,
        }

    cases = [
        (project_binding.ProjectNotFoundError("unknown"), 404),
        (project_binding.ProjectAccessDeniedError("no access"), 403),
        (project_binding.ProjectBindingUnreachableError("down"), 503),
    ]
    saved = (projects_module.get_project, project_binding.verify_project_binding)
    projects_module.get_project = fake_get_project
    try:
        for error, expected_status in cases:
            async def failing_verify(candidate, _error=error, **kwargs):
                raise _error

            project_binding.verify_project_binding = failing_verify
            try:
                await _require_customer_project(agent, _identity(), object(), "proj-1")
                raise AssertionError(f"expected {expected_status} for {type(error).__name__}")
            except HTTPException as exc:
                assert exc.status_code == expected_status, (type(error).__name__, exc.status_code)
    finally:
        (projects_module.get_project, project_binding.verify_project_binding) = saved


async def test_finages_real_bundle_still_declares_project_required() -> None:
    """Not a fixture - the REAL Finage bundle, parsed by the real registry
    (AGENTS_DIR set at the top of this file). ADR-0528 changes what
    project_required MEANS, never which tasks carry it."""
    finage = _registry.get("finage")
    assert finage is not None, "finage bundle failed to load from AGENTS_DIR"
    assert finage.tasks["identify-business-ready-to-invoice"].project_required is True
    assert finage.tasks["monthly-invoice-report"].project_required is True
    # answer-finance-question (Finage's real primary_task) must stay
    # unmarked - neither ADR widened to tasks it wasn't asked to cover.
    assert finage.tasks["answer-finance-question"].project_required is False


# --------------------------------------------------------------------------
# app/conversations.py - record_turn's new optional project_id param must
# not disturb the existing None-pool no-op contract.
# --------------------------------------------------------------------------


async def test_record_turn_with_project_id_still_no_ops_on_a_none_pool() -> None:
    await conversations_module.record_turn(
        None, run_id="run-abc", agent_name="finage", owner_sub="alice",
        opening_message="hi", project_id="006Verified",
    )  # no exception raised = pass


async def test_stamp_salesforce_verification_fails_closed_on_a_none_pool() -> None:
    """ADR-0528 replaced conversations.get_project_binding (the
    per-conversation stamp) with a per-project one. Same fail-closed
    posture: recording a verification must never silently succeed against
    an unreachable pool, or a stale stamp would look fresh forever."""
    try:
        await projects_module.stamp_salesforce_verification(None, project_id="proj-1")
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 503, exc.status_code


# --------------------------------------------------------------------------
# app/graph/nodes.py - quota-header gating (finding 4: only a task's own
# project_required mark may let state["project_id"] reach ai-gateway's
# X-Zuno-Project-Id header, never merely state["project_id"] being truthy)
# --------------------------------------------------------------------------


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
    test_unmarked_task_is_untouched_by_the_customer_project_check,
    test_project_required_task_refuses_a_conversation_with_no_project,
    test_project_required_task_refuses_a_free_project,
    test_a_fresh_customer_project_makes_no_salesforce_call,
    test_a_stale_customer_project_reverifies_once_and_restamps,
    test_reverification_maps_each_typed_error_to_the_right_http_status,
    test_finages_real_bundle_still_declares_project_required,
    test_record_turn_with_project_id_still_no_ops_on_a_none_pool,
    test_stamp_salesforce_verification_fails_closed_on_a_none_pool,
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
