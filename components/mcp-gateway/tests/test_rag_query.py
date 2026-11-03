"""WP-156/WP-168: search_technical_docs answers from UnifAI's bearer RAG endpoint
(with the caller's own token, Keycloak or OpenShift) over the CONFLUENCE sources and the
WEB sources (the Red Hat product documentation), interleaved."""
from __future__ import annotations

import asyncio
import os
import sys

import httpx
import pytest

COMPONENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, COMPONENT_DIR)

from app.handlers import rag_query  # noqa: E402

JWT = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJjb25zdWx0YW50LTAxIn0.c2ln"
OPENSHIFT_TOKEN = "sha256~abcdef"


def _run(monkeypatch, bearer_token, handler):
    seen = []

    def transport_handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(transport_handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(rag_query.httpx, "AsyncClient", client_factory)
    result = asyncio.run(
        rag_query.handle(
            {"query": "schedule satellite", "top_k": 3},
            "consultant-01",
            bearer_token=bearer_token,
            caller_groups=["consultant"],
        )
    )
    return result, seen


UNIFAI_MATCH = {
    "id": "c1",
    "score": 0.7,
    "content": "# S0R42 : Schedule Satellite",
    "metadata": {"title": "S0R42 : Schedule Satellite", "url": "https://wiki/S0R42"},
}
WEB_MATCHES = [
    {"id": "w1", "score": 0.5, "content": "a", "metadata": {"title": "A", "url": "https://docs.redhat.com/a"}},
    {"id": "w2", "score": 0.3, "content": "b", "metadata": {"title": "B", "url": "https://docs.redhat.com/b"}},
]


def _by_type(confluence_response, web_response):
    def handler(request):
        if request.url.params.get("sourceType") == "WEB":
            return web_response
        return confluence_response
    return handler


def test_a_keycloak_jwt_queries_both_source_types_with_the_callers_token(monkeypatch):
    result, seen = _run(monkeypatch, JWT, _by_type(
        httpx.Response(200, json={"matches": [UNIFAI_MATCH]}),
        httpx.Response(200, json={"matches": WEB_MATCHES}),
    ))

    assert {r.url.host for r in seen} == {"unifai-rag-server.zuno-unifai.svc"}
    assert sorted(r.url.params["sourceType"] for r in seen) == ["CONFLUENCE", "WEB"]
    for request in seen:
        assert request.method == "GET"
        assert request.url.path == "/api/sources/query.bearer"
        assert request.url.params["tags"] == "knowledge.tech"
        assert request.url.params["top_k_results"] == "3"
        assert request.headers["authorization"] == f"Bearer {JWT}"
    # Interleaved, Confluence first, capped at top_k=3.
    assert [r["id"] for r in result["results"]] == ["c1", "w1", "w2"]
    assert result["results"][0] == {
        "id": "c1",
        "source": "https://wiki/S0R42",
        "title": "S0R42 : Schedule Satellite",
        "snippet": "# S0R42 : Schedule Satellite",
        "score": 0.7,
        # No classification in the chunk metadata: C2, fail closed (WP-187).
        "classification": "C2",
    }


def test_one_failed_source_type_leaves_the_other(monkeypatch):
    result, _ = _run(monkeypatch, JWT, _by_type(
        httpx.Response(401, json={"detail": "invalid bearer token"}),
        httpx.Response(200, json={"matches": WEB_MATCHES}),
    ))
    assert [r["id"] for r in result["results"]] == ["w1", "w2"]


def test_an_openshift_token_is_forwarded_to_unifai_too(monkeypatch):
    result, seen = _run(monkeypatch, OPENSHIFT_TOKEN, _by_type(
        httpx.Response(200, json={"matches": [UNIFAI_MATCH]}),
        httpx.Response(200, json={"matches": WEB_MATCHES[:1]}),
    ))
    assert all(r.headers["authorization"] == f"Bearer {OPENSHIFT_TOKEN}" for r in seen)
    assert [r["id"] for r in result["results"]] == ["c1", "w1"]


def test_all_source_types_failing_is_reported_not_raised(monkeypatch):
    result, _ = _run(monkeypatch, JWT, lambda request: httpx.Response(503))
    assert "error" in result
    assert "503" in result["error"]


def test_a_call_without_a_bearer_token_contacts_no_backend(monkeypatch):
    seen = []
    monkeypatch.setattr(rag_query.httpx, "AsyncClient", lambda *a, **k: seen.append(1))
    result = asyncio.run(rag_query.handle({"query": "satellite"}, "consultant-01", bearer_token=""))
    assert "bearer token" in result["error"]
    assert seen == []


def test_an_empty_query_contacts_no_backend(monkeypatch):
    seen = []
    monkeypatch.setattr(rag_query.httpx, "AsyncClient", lambda *a, **k: seen.append(1))
    result = asyncio.run(rag_query.handle({"query": "  "}, "consultant-01", bearer_token=JWT))
    assert result == {"error": "query is required"}
    assert seen == []


@pytest.mark.parametrize("confluence,web", [
    (httpx.Response(200, json={"matches": [UNIFAI_MATCH]}), httpx.Response(200, json={"matches": WEB_MATCHES})),
    (httpx.Response(401, json={"detail": "invalid bearer token"}), httpx.Response(403, json={})),
    (httpx.Response(500, json={}), httpx.Response(503, json={})),
], ids=["answer", "refusal", "server-error"])
def test_the_retrieval_path_only_reads(monkeypatch, confluence, web):
    """ADR-0205 (WP-186): the indexed path never writes. The invariant test that went with the retired
    rag-service is replaced by this one: whatever the outcome, every request the handler sends is a GET
    with no body."""
    _, seen = _run(monkeypatch, JWT, _by_type(confluence, web))
    assert seen, "the handler sent no request"
    for request in seen:
        assert request.method == "GET"
        assert request.content == b""


def test_the_handler_source_has_no_write_call():
    source = open(rag_query.__file__, encoding="utf-8").read()
    for verb in (".post(", ".put(", ".patch(", ".delete("):
        assert verb not in source, f"rag_query.py calls {verb}: the retrieval path must stay read only"


def test_the_chunk_classification_is_returned(monkeypatch):
    """WP-187: the source's classification, written on every chunk by UnifAI
    (operator 0.1.50), is what the tool returns: Confluence C2, Red Hat docs C1."""
    confluence = dict(UNIFAI_MATCH, metadata=dict(UNIFAI_MATCH["metadata"], classification="C2"))
    web = [dict(m, metadata=dict(m["metadata"], classification="C1")) for m in WEB_MATCHES]
    result, _ = _run(monkeypatch, JWT, _by_type(
        httpx.Response(200, json={"matches": [confluence]}),
        httpx.Response(200, json={"matches": web}),
    ))
    assert [(r["id"], r["classification"]) for r in result["results"]] == [("c1", "C2"), ("w1", "C1"), ("w2", "C1")]


def test_a_missing_or_invalid_classification_is_c2():
    from app.handlers import rag_query

    assert rag_query._classification({}) == "C2"
    assert rag_query._classification({"classification": ""}) == "C2"
    assert rag_query._classification({"classification": "secret"}) == "C2"
    assert rag_query._classification({"classification": "C9"}) == "C2"
    assert rag_query._classification({"classification": "c3"}) == "C3"
    assert rag_query._classification({"classification": "C4"}) == "C4"
    assert rag_query._classification({"classification": "C1"}) == "C1"
