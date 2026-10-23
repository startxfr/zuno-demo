"""WP-156: search_technical_docs answers from UnifAI's bearer RAG endpoint
(with the caller's own token, Keycloak or OpenShift) and rag-service (the Red
Hat product documentation, until WP-168), interleaved."""
from __future__ import annotations

import asyncio
import os
import sys

import httpx

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
RAG_SERVICE_RESULTS = [
    {"id": "r1", "source": "https://docs.redhat.com/a", "title": "A", "snippet": "a", "score": 3.1},
    {"id": "r2", "source": "https://docs.redhat.com/b", "title": "B", "snippet": "b", "score": 2.0},
]


def _both(unifai_response, rag_service_response):
    def handler(request):
        if request.url.host == "unifai-rag-server.zuno-unifai.svc":
            return unifai_response
        return rag_service_response
    return handler


def test_a_keycloak_jwt_queries_unifai_with_the_callers_token_and_rag_service(monkeypatch):
    result, seen = _run(monkeypatch, JWT, _both(
        httpx.Response(200, json={"matches": [UNIFAI_MATCH]}),
        httpx.Response(200, json={"results": RAG_SERVICE_RESULTS}),
    ))

    unifai = [r for r in seen if r.url.host == "unifai-rag-server.zuno-unifai.svc"]
    rag_service = [r for r in seen if r.url.host == "rag-service.zuno-data.svc"]
    assert len(unifai) == 1 and len(rag_service) == 1
    request = unifai[0]
    assert request.method == "GET"
    assert request.url.path == "/api/sources/query.bearer"
    assert request.url.params["tags"] == "knowledge.tech"
    assert request.url.params["sourceType"] == "CONFLUENCE"
    assert request.url.params["top_k_results"] == "3"
    assert request.headers["authorization"] == f"Bearer {JWT}"
    assert "authorization" not in rag_service[0].headers
    # Interleaved, UnifAI first, capped at top_k=3.
    assert [r["id"] for r in result["results"]] == ["c1", "r1", "r2"]
    assert result["results"][0] == {
        "id": "c1",
        "source": "https://wiki/S0R42",
        "title": "S0R42 : Schedule Satellite",
        "snippet": "# S0R42 : Schedule Satellite",
        "score": 0.7,
        "classification": "C1",
    }


def test_one_failed_source_leaves_the_other(monkeypatch):
    result, _ = _run(monkeypatch, JWT, _both(
        httpx.Response(401, json={"detail": "invalid bearer token"}),
        httpx.Response(200, json={"results": RAG_SERVICE_RESULTS}),
    ))
    assert [r["id"] for r in result["results"]] == ["r1", "r2"]


def test_an_openshift_token_is_forwarded_to_unifai_too(monkeypatch):
    result, seen = _run(monkeypatch, OPENSHIFT_TOKEN, _both(
        httpx.Response(200, json={"matches": [UNIFAI_MATCH]}),
        httpx.Response(200, json={"results": RAG_SERVICE_RESULTS[:1]}),
    ))
    unifai = [r for r in seen if r.url.host == "unifai-rag-server.zuno-unifai.svc"]
    assert unifai[0].headers["authorization"] == f"Bearer {OPENSHIFT_TOKEN}"
    assert [r["id"] for r in result["results"]] == ["c1", "r1"]


def test_both_sources_failing_is_reported_not_raised(monkeypatch):
    result, _ = _run(monkeypatch, JWT, lambda request: httpx.Response(503))
    assert "error" in result
    assert "503" in result["error"]


def test_an_empty_query_contacts_no_backend(monkeypatch):
    seen = []
    monkeypatch.setattr(rag_query.httpx, "AsyncClient", lambda *a, **k: seen.append(1))
    result = asyncio.run(rag_query.handle({"query": "  "}, "consultant-01", bearer_token=JWT))
    assert result == {"error": "query is required"}
    assert seen == []
