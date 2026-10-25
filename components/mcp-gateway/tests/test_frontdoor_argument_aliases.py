"""The /mcp front door tolerates common aliases of a search tool's `query` argument and keeps tool errors short.

Run from the component directory:  cd components/mcp-gateway && python3 -m pytest tests/test_frontdoor_argument_aliases.py
"""
from __future__ import annotations

import asyncio
import os
import sys

COMPONENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, COMPONENT_DIR)

from app import mcp_frontdoor  # noqa: E402
from app.mcp_frontdoor import normalise_arguments  # noqa: E402

SEARCH = ["confluence.page.search", "search_confluence"]


def test_aliases_map_to_query_on_search_tools():
    for alias in ("search_query", "q", "text", "query_text", "search_term", "keywords"):
        assert normalise_arguments(SEARCH, {alias: "satellite scheduling"}) == {"query": "satellite scheduling"}


def test_other_arguments_are_kept_and_alias_keys_dropped():
    out = normalise_arguments(SEARCH, {"search_query": "x", "limit": 5, "q": "y"})
    assert out == {"query": "x", "limit": 5}


def test_an_explicit_query_wins_and_is_left_alone():
    args = {"query": "real", "q": "other"}
    assert normalise_arguments(SEARCH, args) == args


def test_non_search_tools_are_not_rewritten():
    args = {"q": "x"}
    assert normalise_arguments(["git.repository.list"], args) == args
    assert normalise_arguments(["aap.cluster.audit"], args) == args


def test_empty_or_non_string_aliases_do_nothing():
    assert normalise_arguments(SEARCH, {"q": "  "}) == {"q": "  "}
    assert normalise_arguments(SEARCH, {"q": 5}) == {"q": 5}


def test_the_single_free_string_argument_becomes_the_query():
    assert normalise_arguments(SEARCH, {"title": "OpenShift Satellite"}) == {"query": "OpenShift Satellite"}
    assert normalise_arguments(SEARCH, {"page_title": "x", "space": "SXSI"}) == {"query": "x", "space": "SXSI"}


def test_two_free_string_arguments_are_ambiguous_and_left_alone():
    args = {"title": "a", "topic": "b"}
    assert normalise_arguments(SEARCH, args) == args


def test_a_numeric_string_limit_becomes_an_integer():
    assert normalise_arguments(SEARCH, {"query": "x", "limit": "5"}) == {"query": "x", "limit": 5}
    assert normalise_arguments(SEARCH, {"query": "x", "limit": "many"}) == {"query": "x", "limit": "many"}


def test_a_validation_failure_becomes_a_plain_instruction():
    err = ValueError("confluence MCP server returned a tool error: Error executing tool search_pages: 1 validation error for search_pagesArguments")
    assert mcp_frontdoor._short_error(err) == "No result: the search arguments did not match the tool's schema."


def test_short_error_has_one_line_no_validator_url_and_is_capped():
    long = "boom happened\nquery\n  detail\n    For further information visit https://errors.pydantic.dev/2.7/v/missing"
    assert mcp_frontdoor._short_error(ValueError(long)) == "boom happened"
    assert len(mcp_frontdoor._short_error(ValueError("x" * 1000))) == 200
    assert mcp_frontdoor._short_error(ValueError("")) == "the tool call failed"


class _Binding:
    def __init__(self, names):
        self._names = names

    def all_names(self):
        return self._names


class _Registry:
    def resolve(self, name):
        return _Binding(SEARCH) if name in SEARCH else None


def _call(arguments, invoke):
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "confluence.page.search", "arguments": arguments}}
    surface = type("S", (), {"capabilities": ["confluence.page.search"]})()
    return asyncio.run(mcp_frontdoor.dispatch(
        message, policy_store=None, binding_registry=_Registry(), identity=type("I", (), {"sub": "u"})(),
        classification="C1", invoke_tool=invoke, surface=surface,
    ))


def test_dispatch_sends_the_canonical_argument_downstream():
    seen = {}

    async def invoke(tool_name, arguments):
        seen.update(arguments)
        return {"results": []}

    out = _call({"search_query": "satellite"}, invoke)
    assert seen == {"query": "satellite"} and out["result"]["isError"] is False


def test_dispatch_returns_a_short_neutral_tool_error():
    async def invoke(tool_name, arguments):
        raise ValueError("boom\nsecond line with detail\nFor further information visit https://errors.pydantic.dev/x")

    out = _call({"query": "x"}, invoke)
    assert out["result"]["isError"] is True and out["result"]["content"][0]["text"] == "boom"


def test_dispatch_still_refuses_a_tool_that_is_not_exposed():
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "confluence.page.search", "arguments": {"q": "x"}}}
    surface = type("S", (), {"capabilities": ["knowledge.tech.search"]})()

    async def invoke(**kw):  # pragma: no cover - must not be reached
        raise AssertionError("invoked")

    out = asyncio.run(mcp_frontdoor.dispatch(
        message, policy_store=None, binding_registry=_Registry(), identity=type("I", (), {"sub": "u"})(),
        classification="C1", invoke_tool=invoke, surface=surface,
    ))
    assert out["result"]["isError"] is True and "not exposed" in out["result"]["content"][0]["text"]


def test_an_empty_search_is_answered_like_an_empty_result_without_calling_the_tool():
    called = []

    async def invoke(tool_name, arguments):
        called.append(arguments)
        return {}

    for arguments in ({}, {"query": "  "}, {"limit": 5}):
        out = _call(arguments, invoke)
        result = out["result"]
        assert result["isError"] is False
        assert result["content"][0]["text"] == "No pages found: the search text was empty."
    assert called == []


def test_error_texts_never_tell_the_model_what_to_do():
    texts = [
        mcp_frontdoor._short_error(ValueError("1 validation error for X")),
        mcp_frontdoor._short_error(ValueError("")),
    ]
    for text in texts:
        assert not any(word in text.lower() for word in ("send ", "retry", "please", "try again"))
