"""WP-156: search_technical_docs routes a Keycloak JWT to UnifAI's bearer RAG
endpoint with the caller's own token, and keeps any other token (OpenShift
Lightspeed's) on rag-service until UnifAI reviews Kubernetes tokens."""
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


def test_a_keycloak_jwt_goes_to_unifai_with_the_callers_token(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"matches": [{
            "id": "c1",
            "score": 0.7,
            "content": "# S0R42 : Schedule Satellite",
            "metadata": {"title": "S0R42 : Schedule Satellite", "url": "https://wiki/S0R42"},
        }]})

    result, seen = _run(monkeypatch, JWT, handler)

    assert len(seen) == 1
    request = seen[0]
    assert request.method == "GET"
    assert request.url.host == "unifai-rag-server.zuno-unifai.svc"
    assert request.url.path == "/api/sources/query.bearer"
    assert request.url.params["tags"] == "knowledge.tech"
    assert request.url.params["sourceType"] == "CONFLUENCE"
    assert request.url.params["top_k_results"] == "3"
    assert request.headers["authorization"] == f"Bearer {JWT}"
    assert result == {"results": [{
        "id": "c1",
        "source": "https://wiki/S0R42",
        "title": "S0R42 : Schedule Satellite",
        "snippet": "# S0R42 : Schedule Satellite",
        "score": 0.7,
        "classification": "C1",
    }]}


def test_an_openshift_token_stays_on_rag_service(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"results": [{"id": "r1"}]})

    result, seen = _run(monkeypatch, OPENSHIFT_TOKEN, handler)

    assert len(seen) == 1
    assert seen[0].method == "POST"
    assert seen[0].url.host == "rag-service.zuno-data.svc"
    assert "authorization" not in seen[0].headers
    assert result == {"results": [{"id": "r1"}]}


def test_a_unifai_refusal_is_reported_not_raised(monkeypatch):
    result, _ = _run(monkeypatch, JWT, lambda request: httpx.Response(401, json={"detail": "invalid bearer token"}))
    assert "error" in result
    assert "401" in result["error"]


def test_an_empty_query_contacts_no_backend(monkeypatch):
    seen = []
    monkeypatch.setattr(rag_query.httpx, "AsyncClient", lambda *a, **k: seen.append(1))
    result = asyncio.run(rag_query.handle({"query": "  "}, "consultant-01", bearer_token=JWT))
    assert result == {"error": "query is required"}
    assert seen == []
