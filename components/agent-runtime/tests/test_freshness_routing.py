#!/usr/bin/env python3
"""WP-24 (ADR-0205/ADR-0109) acceptance tests: the live-read trigger
(_live_read_trigger_reason / should_call_tools) and the source_mode
computation (_compute_source_mode) that together implement "prefer
indexed knowledge for read, live tools for freshness" and "traces show
whether a response used indexed knowledge, live verification, or both."
Same no-pytest/no-live-cluster style as tests/test_retrieve_metadata.py.

Run directly:

    cd components/agent-runtime && python3 tests/test_freshness_routing.py
"""
from __future__ import annotations

import os
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

from app.graph import nodes  # noqa: E402
from app.graph.nodes import (  # noqa: E402
    _ANSWER_TASK,
    _compute_source_mode,
    _live_read_trigger_reason,
    should_call_tools,
)


# --- _live_read_trigger_reason / should_call_tools --------------------------


def test_explicit_current_state_question_triggers_a_live_read() -> None:
    state = {"message": "what is the current OpenShift version", "retrieved_docs": []}
    reason = _live_read_trigger_reason(state)
    assert reason is not None
    assert "current-state question" in reason
    assert should_call_tools(state) == "tool_call"


def test_a_freshness_sensitive_domain_triggers_a_live_read_even_without_trigger_words() -> None:
    state = {
        "message": "what's the status of this deal",  # no trigger word
        "retrieved_docs": [{"domain": "knowledge.sales", "stale": False}],
    }
    reason = _live_read_trigger_reason(state)
    assert reason is not None
    assert "knowledge.sales" in reason
    assert should_call_tools(state) == "tool_call"


def test_a_stale_retrieved_document_triggers_a_live_read() -> None:
    state = {
        "message": "how do I configure this",
        "retrieved_docs": [{"domain": "knowledge.tech", "stale": True, "source": "https://docs.test/x"}],
    }
    reason = _live_read_trigger_reason(state)
    assert reason is not None
    assert "exceeded its freshness window" in reason
    assert should_call_tools(state) == "tool_call"


def test_a_normal_question_over_fresh_tech_docs_does_not_trigger_a_live_read() -> None:
    state = {
        "message": "how do I configure a ServingRuntime",
        "retrieved_docs": [{"domain": "knowledge.tech", "stale": False}],
    }
    assert _live_read_trigger_reason(state) is None
    assert should_call_tools(state) == "reason"


def test_no_retrieved_docs_and_no_trigger_word_does_not_trigger_a_live_read() -> None:
    state = {"message": "how does pgvector hybrid search work", "retrieved_docs": []}
    assert _live_read_trigger_reason(state) is None
    assert should_call_tools(state) == "reason"


# --- _compute_source_mode ----------------------------------------------------


def test_source_mode_indexed_only() -> None:
    state = {"retrieved_docs": [{"source": "x", "title": "X"}], "tool_results": {}}
    assert _compute_source_mode(state) == "indexed"


def test_source_mode_live_only() -> None:
    state = {
        "retrieved_docs": [],
        "tool_results": {"search_confluence": {"result": {"results": [{"title": "Y", "url": "y"}]}}},
    }
    assert _compute_source_mode(state) == "live"


def test_source_mode_both() -> None:
    state = {
        "retrieved_docs": [{"source": "x", "title": "X"}],
        "tool_results": {"search_confluence": {"result": {"results": [{"title": "Y", "url": "y"}]}}},
    }
    assert _compute_source_mode(state) == "both"


def test_source_mode_none_when_nothing_contributed() -> None:
    """"No silent substitution": a turn where retrieval was skipped
    (denied domain) and no live tool call happened either must be
    honestly reported as "none", never defaulted to "indexed" as if
    something had actually been retrieved."""
    state = {"retrieved_docs": [], "tool_results": {}}
    assert _compute_source_mode(state) == "none"


def test_source_mode_ignores_an_empty_confluence_result_as_not_live() -> None:
    # A tool call that ran but returned zero results must not count as
    # "live" contributing to the answer - only actual results do.
    state = {
        "retrieved_docs": [{"source": "x", "title": "X"}],
        "tool_results": {"search_confluence": {"result": {"results": []}}},
    }
    assert _compute_source_mode(state) == "indexed"


# --- WP-24 write-path invariant ---------------------------------------------

_WRITE_TOOL_NAME_PREFIXES = ("create_", "update_", "delete_", "write_")


def test_the_answer_task_never_declares_a_write_capable_tool() -> None:
    """ADR-0205: "RAG stays write-free - a mutation of a source system
    goes through a live tool capability, never through indexed
    retrieval." tool_call_node's only live-read path is whatever this
    task declares (currently search_confluence, web_search - both reads);
    this catches a future edit that accidentally adds a write-shaped tool
    name to a task the retrieval flow can reach."""
    for tool_name in _ANSWER_TASK.allowed_tools:
        assert not tool_name.startswith(_WRITE_TOOL_NAME_PREFIXES), (
            f"answer-technical-question.md declares '{tool_name}', which looks write-capable - "
            "the retrieval flow (tool_call_node) must only ever reach read-only tools"
        )


def test_tool_call_node_source_hardcodes_search_confluence_not_a_variable_tool_name() -> None:
    """Structural guard: tool_call_node's invoke_tool call must name
    search_confluence as a literal, not build a tool name from caller
    input or retrieved content - the only way this node could ever
    invoke a write tool is if that changed."""
    import inspect

    source = inspect.getsource(nodes.tool_call_node)
    assert 'tool_name="search_confluence"' in source


TESTS = [
    test_explicit_current_state_question_triggers_a_live_read,
    test_a_freshness_sensitive_domain_triggers_a_live_read_even_without_trigger_words,
    test_a_stale_retrieved_document_triggers_a_live_read,
    test_a_normal_question_over_fresh_tech_docs_does_not_trigger_a_live_read,
    test_no_retrieved_docs_and_no_trigger_word_does_not_trigger_a_live_read,
    test_source_mode_indexed_only,
    test_source_mode_live_only,
    test_source_mode_both,
    test_source_mode_none_when_nothing_contributed,
    test_source_mode_ignores_an_empty_confluence_result_as_not_live,
    test_the_answer_task_never_declares_a_write_capable_tool,
    test_tool_call_node_source_hardcodes_search_confluence_not_a_variable_tool_name,
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
