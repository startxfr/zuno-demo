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

import os
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))
os.environ.setdefault(
    "KNOWLEDGE_POLICY_PATH", str(_REPO_ROOT / "policies" / "knowledge" / "knowledge-policy.yaml")
)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

from app.graph import arkos_nodes  # noqa: E402


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


def test_arkos_declares_the_confluence_and_drive_capabilities_from_its_task() -> None:
    """Sanity check against the real checked-in bundle - confirms the
    module-level singletons resolved the actual draft-architecture-
    testimonial task, not a stale/empty one."""
    assert "confluence.page.search" in arkos_nodes._DRAFT_TASK.allowed_tools
    assert "drive.document.create" in arkos_nodes._DRAFT_TASK.allowed_tools
    assert "knowledge.tech" in arkos_nodes._DRAFT_TASK.allowed_knowledge
    assert "knowledge.project" in arkos_nodes._DRAFT_TASK.allowed_knowledge


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
    test_arkos_declares_the_confluence_and_drive_capabilities_from_its_task,
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
