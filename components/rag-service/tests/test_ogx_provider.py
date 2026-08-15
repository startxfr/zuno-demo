#!/usr/bin/env python3
"""ADR-0322 tests for the OGX-backed RAG provider prototype:
app/ogx_provider.py. Mocks the HTTP layer (no live OGXServer exists to
call against - see that module's docstring) to prove the *selection*
gate, the *filter* logic (product/version/ACL fail-closed, mirroring
app/search.py:_filter_clause's semantics) and the *response mapping*
(OpenAI Vector Store search shape -> app/schemas.py:SearchResult shape)
are each correct in isolation.

Same plain-function/no-pytest style as tests/test_search_filters.py.

Run directly:

    cd components/rag-service && python3 tests/test_ogx_provider.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

from app import ogx_provider  # noqa: E402


def _reset_provider_env(**overrides: str) -> None:
    for key in ("RAG_PROVIDER", "OGX_BASE_URL", "OGX_VECTOR_STORE_ID", "OGX_API_TOKEN_ENV", "OGX_TIMEOUT_SECONDS"):
        os.environ.pop(key, None)
    os.environ.update(overrides)
    ogx_provider.RAG_PROVIDER = os.getenv("RAG_PROVIDER", "pgvector").strip().lower()
    ogx_provider.OGX_BASE_URL = os.getenv("OGX_BASE_URL", "")
    ogx_provider.OGX_VECTOR_STORE_ID = os.getenv("OGX_VECTOR_STORE_ID", "")
    ogx_provider.OGX_API_TOKEN_ENV = os.getenv("OGX_API_TOKEN_ENV", "OGX_API_TOKEN")
    ogx_provider.OGX_TIMEOUT_SECONDS = float(os.getenv("OGX_TIMEOUT_SECONDS", "10"))


def test_ogx_disabled_by_default() -> None:
    _reset_provider_env()
    assert ogx_provider.enabled() is False
    assert ogx_provider.should_use_ogx() is False


def test_ogx_enabled_only_when_explicitly_selected() -> None:
    _reset_provider_env(RAG_PROVIDER="ogx")
    assert ogx_provider.should_use_ogx() is True

    _reset_provider_env(RAG_PROVIDER="pgvector")
    assert ogx_provider.should_use_ogx() is False

    _reset_provider_env(RAG_PROVIDER="OGX")  # case-insensitive
    assert ogx_provider.should_use_ogx() is True


def test_passes_filters_product_and_version_exact_match() -> None:
    attrs = {"product": "openshift-ai", "version": "3.5"}
    assert ogx_provider._passes_filters(attrs, product=None, version=None, caller_groups=[]) is True
    assert ogx_provider._passes_filters(attrs, product="openshift-ai", version=None, caller_groups=[]) is True
    assert ogx_provider._passes_filters(attrs, product="other-product", version=None, caller_groups=[]) is False
    assert ogx_provider._passes_filters(attrs, product=None, version="4.0", caller_groups=[]) is False


def test_passes_filters_acl_fail_closed() -> None:
    """ADR-0046/ADR-0322 Security considerations: an ACL-restricted
    document is excluded unless the caller's groups intersect - even when
    caller_groups is empty (fail closed, never fail open), same semantics
    as app/search.py:_filter_clause.
    """
    restricted = {"acl_groups": ["consultant"]}
    unrestricted = {}

    assert ogx_provider._passes_filters(restricted, None, None, caller_groups=[]) is False
    assert ogx_provider._passes_filters(restricted, None, None, caller_groups=["other-group"]) is False
    assert ogx_provider._passes_filters(restricted, None, None, caller_groups=["consultant"]) is True
    assert ogx_provider._passes_filters(unrestricted, None, None, caller_groups=[]) is True


def test_row_to_result_maps_openai_vector_store_shape() -> None:
    row = {
        "file_id": "doc-42",
        "score": 0.87654,
        "content": [{"text": "first part. "}, {"text": "second part."}],
        "attributes": {
            "source": "https://docs.redhat.com/x",
            "title": "Sizing GPUs",
            "classification": "C2",
            "language": "fr",
            "product": "openshift-ai",
            "version": "3.5",
        },
    }
    doc = ogx_provider._row_to_result(row)
    assert doc["id"] == "doc-42"
    assert doc["source"] == "https://docs.redhat.com/x"
    assert doc["title"] == "Sizing GPUs"
    assert doc["snippet"] == "first part.  second part."
    assert doc["score"] == 0.87654
    assert doc["classification"] == "C2"
    assert doc["language"] == "fr"
    assert doc["product"] == "openshift-ai"
    assert doc["version"] == "3.5"
    assert doc["stale"] is False


def test_row_to_result_defaults_untagged_classification_to_c1() -> None:
    """ADR-0046: a document with no classification tag defaults to C1,
    the same baseline app/search.py:_row_to_doc uses - never invent a
    higher-than-declared classification."""
    doc = ogx_provider._row_to_result({"file_id": "x", "attributes": {}})
    assert doc["classification"] == "C1"


def test_row_to_result_computes_staleness_via_shared_helper() -> None:
    doc = ogx_provider._row_to_result({"file_id": "x", "attributes": {"stale_after": "2020-01-01"}})
    assert doc["stale"] is True


def test_row_to_result_flags_freshness_untrusted_via_shared_helper() -> None:
    """WP-24/ADR-0205: same freshness-untrusted rule as
    app/search.py:_row_to_doc, computed through the shared
    _is_freshness_untrusted helper - schema parity between the two
    providers is the ADR-0322 acceptance bar (this module's docstring)."""
    untrusted = ogx_provider._row_to_result({"file_id": "x", "attributes": {}})
    assert untrusted["freshness_untrusted"] is True

    trusted = ogx_provider._row_to_result({"file_id": "y", "attributes": {"indexed_at": "2026-08-01T00:00:00Z"}})
    assert trusted["freshness_untrusted"] is False

    exempt = ogx_provider._row_to_result({"file_id": "z", "attributes": {"domain": "knowledge.sxa-legacy"}})
    assert exempt["freshness_untrusted"] is False


def test_ogx_search_without_endpoint_fails_loudly() -> None:
    _reset_provider_env(RAG_PROVIDER="ogx")

    async def run():
        try:
            await ogx_provider.ogx_search("gpu sizing", top_k=5)
            raise AssertionError("expected OgxProviderError")
        except ogx_provider.OgxProviderError as exc:
            assert "OGX_BASE_URL" in str(exc)

    asyncio.run(run())


class _FakeResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


class _FakeAsyncClient:
    def __init__(self, body, captured):
        self._body = body
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        self._captured["url"] = url
        self._captured["json"] = json
        self._captured["headers"] = headers
        return _FakeResponse(self._body)


def test_ogx_search_calls_the_documented_vector_store_search_url() -> None:
    _reset_provider_env(RAG_PROVIDER="ogx", OGX_BASE_URL="http://ogx.example:8321", OGX_VECTOR_STORE_ID="vs-zuno")
    captured = {}
    body = {"data": []}

    async def run():
        with mock.patch("httpx.AsyncClient", return_value=_FakeAsyncClient(body, captured)):
            result = await ogx_provider.ogx_search("gpu sizing", top_k=5)
        assert result == {"results": [], "vector_search_used": True}

    asyncio.run(run())
    assert captured["url"] == "http://ogx.example:8321/v1/vector_stores/vs-zuno/search"
    assert captured["json"]["query"] == "gpu sizing"


def test_ogx_search_applies_client_side_acl_and_product_filters_and_truncates_to_top_k() -> None:
    """Proves the over-fetch-then-filter strategy this module's docstring
    documents: OGX returns more rows than top_k, some fail the caller's
    ACL/product filters, and the final result both respects top_k and
    never leaks a filtered-out row."""
    _reset_provider_env(RAG_PROVIDER="ogx", OGX_BASE_URL="http://ogx.example:8321", OGX_VECTOR_STORE_ID="vs-zuno")
    body = {
        "data": [
            {"file_id": "allowed-1", "score": 0.9, "content": [], "attributes": {"product": "openshift-ai"}},
            {"file_id": "wrong-product", "score": 0.8, "content": [], "attributes": {"product": "other"}},
            {"file_id": "acl-restricted", "score": 0.7, "content": [], "attributes": {"acl_groups": ["secret"]}},
            {"file_id": "allowed-2", "score": 0.6, "content": [], "attributes": {"product": "openshift-ai"}},
            {"file_id": "allowed-3", "score": 0.5, "content": [], "attributes": {"product": "openshift-ai"}},
        ]
    }

    async def run():
        with mock.patch("httpx.AsyncClient", return_value=_FakeAsyncClient(body, {})):
            result = await ogx_provider.ogx_search("gpu sizing", top_k=2, product="openshift-ai", caller_groups=[])
        ids = [r["id"] for r in result["results"]]
        assert ids == ["allowed-1", "allowed-2"], "must skip filtered rows and stop exactly at top_k"
        assert "wrong-product" not in ids
        assert "acl-restricted" not in ids

    asyncio.run(run())


def test_ogx_search_wraps_a_real_httpx_failure() -> None:
    _reset_provider_env(RAG_PROVIDER="ogx", OGX_BASE_URL="http://ogx.example:8321", OGX_VECTOR_STORE_ID="vs-zuno")

    async def run():
        with mock.patch("httpx.AsyncClient") as fake_client_cls:
            fake_client_cls.return_value.__aenter__.side_effect = OSError("connection refused")
            try:
                await ogx_provider.ogx_search("gpu sizing", top_k=5)
                raise AssertionError("expected OgxProviderError")
            except ogx_provider.OgxProviderError:
                pass

    asyncio.run(run())


TESTS = [
    test_ogx_disabled_by_default,
    test_ogx_enabled_only_when_explicitly_selected,
    test_passes_filters_product_and_version_exact_match,
    test_passes_filters_acl_fail_closed,
    test_row_to_result_maps_openai_vector_store_shape,
    test_row_to_result_defaults_untagged_classification_to_c1,
    test_row_to_result_computes_staleness_via_shared_helper,
    test_row_to_result_flags_freshness_untrusted_via_shared_helper,
    test_ogx_search_without_endpoint_fails_loudly,
    test_ogx_search_calls_the_documented_vector_store_search_url,
    test_ogx_search_applies_client_side_acl_and_product_filters_and_truncates_to_top_k,
    test_ogx_search_wraps_a_real_httpx_failure,
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
    _reset_provider_env()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
