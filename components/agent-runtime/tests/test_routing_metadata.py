#!/usr/bin/env python3
"""ADR-0550 (WP-135) tests for app.main's routing-metadata assembly:
_routing_reason's canned prose and _build_routing_metadata's fetch/
placeholder-degradation contract. app.clients.model_router.
fetch_routing_decision is mocked directly - no live ai-gateway/Redis
needed, same pattern test_checkpointing.py already uses for app.main
helpers.

Run directly:

    cd components/agent-runtime && python3 tests/test_routing_metadata.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))
os.environ.setdefault(
    "KNOWLEDGE_POLICY_PATH", str(_REPO_ROOT / "policies" / "knowledge" / "knowledge-policy.yaml")
)

import app.main as main_module  # noqa: E402
from app.main import _build_routing_metadata, _routing_reason  # noqa: E402


# --- _routing_reason --------------------------------------------------------


def test_routing_reason_unknown_execution_location() -> None:
    reason = _routing_reason(
        execution_location="unknown", effective_classification="C1",
        local_only_required=False, fallback_used=False,
    )
    assert reason == "Routing details are unavailable for this response."


def test_routing_reason_local_no_restriction() -> None:
    reason = _routing_reason(
        execution_location="local", effective_classification="C2",
        local_only_required=False, fallback_used=False,
    )
    assert "C2" in reason
    assert "local model" in reason


def test_routing_reason_local_with_local_only_required() -> None:
    reason = _routing_reason(
        execution_location="local", effective_classification="C2",
        local_only_required=True, fallback_used=False,
    )
    assert "local-only" in reason
    assert "C2" in reason


def test_routing_reason_external() -> None:
    reason = _routing_reason(
        execution_location="external", effective_classification="C1",
        local_only_required=False, fallback_used=False,
    )
    assert "external" in reason
    assert "C1" in reason


def test_routing_reason_fallback_used_overrides_execution_location_framing() -> None:
    reason = _routing_reason(
        execution_location="local", effective_classification="C1",
        local_only_required=False, fallback_used=True,
    )
    assert "fallback" in reason
    assert "C1" in reason


def test_routing_reason_never_leaks_raw_exception_text() -> None:
    """Security requirement (WP-135): only canned templates, regardless of
    input - proven by feeding a value shaped like leaked error detail and
    confirming it never appears verbatim anywhere but the classification
    slot itself."""
    poisoned = "connection refused to https://internal.example/secret"
    reason = _routing_reason(
        execution_location="local", effective_classification=poisoned,
        local_only_required=False, fallback_used=False,
    )
    # The classification slot is expected to echo whatever string is
    # passed as effective_classification (it's meant for "C1"/"C2"/"C3"),
    # so the real assertion is that no OTHER, non-templated text leaks in.
    assert reason == f"This request at classification {poisoned} is routed to a local model."


# --- _build_routing_metadata -------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


def test_build_routing_metadata_with_a_published_decision() -> None:
    decision = {
        "provider": "ovhcloud-gpt-oss-120b", "model": "gpt-oss-120b", "kind": "saas",
        "classification": "C1", "fallback_used": False, "fallback_from": None,
    }
    with mock.patch.object(main_module, "fetch_routing_decision", return_value=decision):
        routing = _run(_build_routing_metadata(
            agent="arkos", task_name="draft-architecture-testimonial", project_id=None,
            project_classification=None, effective_classification="C1",
            local_only_required=False, request_id="req-1", bearer_token="t",
        ))
    assert routing.agent == "arkos"
    assert routing.task == "draft-architecture-testimonial"
    assert routing.selected_provider == "ovhcloud-gpt-oss-120b"
    assert routing.selected_model == "gpt-oss-120b"
    assert routing.execution_location == "external"
    assert routing.fallback_used is False
    assert "external" in routing.routing_reason


def test_build_routing_metadata_local_kind_maps_to_local_execution() -> None:
    decision = {
        "provider": "local-gpt-oss", "model": "gpt-oss-20b", "kind": "local",
        "classification": "C2", "fallback_used": False, "fallback_from": None,
    }
    with mock.patch.object(main_module, "fetch_routing_decision", return_value=decision):
        routing = _run(_build_routing_metadata(
            agent="arkos", task_name="draft-architecture-testimonial", project_id="proj-1",
            project_classification="C2", effective_classification="C2",
            local_only_required=True, request_id="req-2", bearer_token="t",
        ))
    assert routing.execution_location == "local"
    assert routing.project_id == "proj-1"
    assert routing.project_classification == "C2"
    assert routing.local_only_required is True


def test_build_routing_metadata_fallback_fields_propagate() -> None:
    decision = {
        "provider": "local-gpt-oss", "model": "gpt-oss-20b", "kind": "local",
        "classification": "C1", "fallback_used": True, "fallback_from": "ovhcloud-gpt-oss-120b",
    }
    with mock.patch.object(main_module, "fetch_routing_decision", return_value=decision):
        routing = _run(_build_routing_metadata(
            agent="arkos", task_name="draft-architecture-testimonial", project_id=None,
            project_classification=None, effective_classification="C1",
            local_only_required=False, request_id="req-3", bearer_token="t",
        ))
    assert routing.fallback_used is True
    assert routing.fallback_from == "ovhcloud-gpt-oss-120b"
    assert "fallback" in routing.routing_reason


def test_build_routing_metadata_degrades_gracefully_when_fetch_returns_none() -> None:
    """The ai-gateway fetch failing (Redis down, 404, network error) must
    never raise - every field falls back to its placeholder, and
    routing_reason says so explicitly rather than pretending to know."""
    with mock.patch.object(main_module, "fetch_routing_decision", return_value=None):
        routing = _run(_build_routing_metadata(
            agent="tekos", task_name="answer-technical-question", project_id=None,
            project_classification=None, effective_classification="C1",
            local_only_required=False, request_id="req-4", bearer_token="t",
        ))
    assert routing.selected_provider == ""
    assert routing.selected_model == ""
    assert routing.execution_location == "unknown"
    assert routing.fallback_used is False
    assert routing.routing_reason == "Routing details are unavailable for this response."


def test_build_routing_metadata_task_name_none_becomes_empty_string() -> None:
    with mock.patch.object(main_module, "fetch_routing_decision", return_value=None):
        routing = _run(_build_routing_metadata(
            agent="tekos", task_name=None, project_id=None, project_classification=None,
            effective_classification=None, local_only_required=False,
            request_id="req-5", bearer_token="t",
        ))
    assert routing.task == ""
    assert routing.project_id == ""
    assert routing.project_classification == ""


def test_build_routing_metadata_falls_back_to_decisions_own_classification_when_state_lacks_one() -> None:
    """effective_classification isn't always populated in state (e.g. a
    node that never ran retrieve_node) - the fetched decision's own
    classification (what ai-gateway actually enforced) is a legitimate
    fallback rather than an empty field."""
    decision = {
        "provider": "local-gpt-oss", "model": "gpt-oss-20b", "kind": "local",
        "classification": "C2", "fallback_used": False, "fallback_from": None,
    }
    with mock.patch.object(main_module, "fetch_routing_decision", return_value=decision):
        routing = _run(_build_routing_metadata(
            agent="arkos", task_name="write-code", project_id=None, project_classification=None,
            effective_classification=None, local_only_required=False,
            request_id="req-6", bearer_token="t",
        ))
    assert routing.effective_classification == "C2"


TESTS = [
    test_routing_reason_unknown_execution_location,
    test_routing_reason_local_no_restriction,
    test_routing_reason_local_with_local_only_required,
    test_routing_reason_external,
    test_routing_reason_fallback_used_overrides_execution_location_framing,
    test_routing_reason_never_leaks_raw_exception_text,
    test_build_routing_metadata_with_a_published_decision,
    test_build_routing_metadata_local_kind_maps_to_local_execution,
    test_build_routing_metadata_fallback_fields_propagate,
    test_build_routing_metadata_degrades_gracefully_when_fetch_returns_none,
    test_build_routing_metadata_task_name_none_becomes_empty_string,
    test_build_routing_metadata_falls_back_to_decisions_own_classification_when_state_lacks_one,
]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
