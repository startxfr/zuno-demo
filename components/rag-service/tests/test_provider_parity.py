#!/usr/bin/env python3
"""ADR-0322 provider-parity tests: "Provider-parity tests prove
metadata/ACL/classification/citation behavior before default-provider
migration" (acceptance criteria).

Neither provider can be exercised end-to-end here - app/search.py's
hybrid_search needs a live PostgreSQL pool, app/ogx_provider.py's
ogx_search needs a live OGXServer (none exists on the test cluster yet,
see that module's docstring). What CAN be proven without either is
**contract parity**: given the same logical document's metadata coming
back from each provider's own backend, do the two row-mapping functions
(app/search.py:_row_to_doc, app/ogx_provider.py:_row_to_result) produce
the same caller-facing fields, and does each provider's full response
shape validate against the exact same app/schemas.py:SearchResponse model
the API returns regardless of which provider served the request. Real
ranking/retrieval-quality parity against a shared corpus is the residual
operator action this WP's brief documents - this file cannot and does not
claim to prove that.

Same plain-function/no-pytest style as tests/test_search_filters.py.

Run directly:

    cd components/rag-service && python3 tests/test_provider_parity.py
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

from app import ogx_provider  # noqa: E402
from app.schemas import SearchResponse, SearchResult  # noqa: E402
from app.search import _row_to_doc  # noqa: E402

# The same logical document, expressed as each provider's own backend
# would return it: a pgvector document_embeddings row (ADR-0046 metadata
# jsonb) and an OGX vector-store search result (attributes).
_BODY_TEXT = "OpenShift AI GPU sizing depends on model parameter count and batch size."

_PGVECTOR_ROW = {
    "id": 42,
    "source": "https://docs.redhat.com/openshift-ai/gpu-sizing",
    "title": "Sizing GPUs for OpenShift AI",
    "content": _BODY_TEXT,
    "metadata": {
        "classification": "C2",
        "language": "fr",
        "product": "openshift-ai",
        "version": "3.5",
        "stale_after": "2020-01-01",  # in the past -> stale
    },
}

_OGX_ROW = {
    "file_id": "doc-42",
    "score": 0.91,
    "content": [{"text": _BODY_TEXT}],
    "attributes": {
        "source": "https://docs.redhat.com/openshift-ai/gpu-sizing",
        "title": "Sizing GPUs for OpenShift AI",
        "classification": "C2",
        "language": "fr",
        "product": "openshift-ai",
        "version": "3.5",
        "stale_after": "2020-01-01",
    },
}

_PARITY_FIELDS = ("source", "title", "snippet", "classification", "language", "product", "version", "stale")


def _project(doc):
    return {field: doc[field] for field in _PARITY_FIELDS}


def test_row_mappers_agree_on_metadata_classification_and_staleness_for_the_same_document() -> None:
    """ADR-0322 acceptance: metadata/classification/citation parity - the
    same document's source/title/classification/language/product/version/
    staleness/snippet must come back identical regardless of provider."""
    pg_doc = _row_to_doc(_PGVECTOR_ROW)
    ogx_doc = ogx_provider._row_to_result(_OGX_ROW)

    assert _project(pg_doc) == _project(ogx_doc), (
        f"provider parity mismatch:\n  pgvector={_project(pg_doc)}\n  ogx={_project(ogx_doc)}"
    )


def test_row_mappers_default_untagged_documents_to_c1_identically() -> None:
    pg_doc = _row_to_doc({"id": 1, "source": "s", "title": "t", "content": "c", "metadata": {}})
    ogx_doc = ogx_provider._row_to_result({"file_id": "1", "content": [], "attributes": {}})
    assert pg_doc["classification"] == ogx_doc["classification"] == "C1"


def test_pgvector_projected_result_validates_against_the_shared_search_result_schema() -> None:
    pg_doc = _row_to_doc(_PGVECTOR_ROW)
    result = SearchResult(
        id=pg_doc["id"],
        source=pg_doc["source"],
        title=pg_doc["title"],
        snippet=pg_doc["snippet"],
        score=0.91,
        classification=pg_doc["classification"],
        language=pg_doc["language"],
        product=pg_doc["product"],
        version=pg_doc["version"],
        stale=pg_doc["stale"],
    )
    SearchResponse(results=[result], vector_search_used=True)  # raises on schema mismatch


def test_ogx_search_full_response_validates_against_the_shared_search_response_schema() -> None:
    """Exercises app/ogx_provider.py's actual public entrypoint end to end
    (HTTP layer mocked, see test_ogx_provider.py for the request/response
    contract this depends on) and proves the exact dict it returns is a
    valid SearchResponse - the same model app/main.py returns for either
    provider, so a caller (Agent Runtime) never needs to know which one
    answered."""

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [_OGX_ROW]}

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            return _FakeResponse()

    async def run():
        with mock.patch.object(ogx_provider, "OGX_BASE_URL", "http://ogx.example:8321"), \
             mock.patch.object(ogx_provider, "OGX_VECTOR_STORE_ID", "vs-zuno"), \
             mock.patch("httpx.AsyncClient", return_value=_FakeAsyncClient()):
            result = await ogx_provider.ogx_search("gpu sizing", top_k=5)
        SearchResponse(**result)  # raises on schema mismatch
        return result

    result = asyncio.run(run())
    assert result["results"][0]["id"] == "doc-42"


TESTS = [
    test_row_mappers_agree_on_metadata_classification_and_staleness_for_the_same_document,
    test_row_mappers_default_untagged_documents_to_c1_identically,
    test_pgvector_projected_result_validates_against_the_shared_search_result_schema,
    test_ogx_search_full_response_validates_against_the_shared_search_response_schema,
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
