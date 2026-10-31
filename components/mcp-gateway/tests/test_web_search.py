"""The web_search handler answers honestly while no provider is configured."""

from __future__ import annotations

import asyncio

from app.handlers import web_search


def _call(arguments):
    return asyncio.run(web_search.handle(arguments, caller_sub="u-1"))


def test_no_results_and_a_message_the_model_reads() -> None:
    result = _call({"query": "What is a namespace in OpenShift?"})
    assert result["available"] is False
    assert result["results"] == []
    assert result["query"] == "What is a namespace in OpenShift?"
    assert "Do not call this tool again" in result["message"]


def test_never_returns_fixed_pages_whatever_the_query() -> None:
    """The former demo stub returned the same two docs.redhat.com / nvidia.com pages for any
    query, which agents cited as sources (tekos scenario #11, 2026-10-25)."""
    for query in ("openshift ai gpu sizing", "namespace", ""):
        result = _call({"query": query})
        assert result["results"] == []
        assert "http" not in str(result)
