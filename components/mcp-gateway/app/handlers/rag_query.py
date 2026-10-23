"""In-process handler for the ``search_technical_docs`` MCP tool
(capability ``knowledge.tech.search``).

WP-156 (ADR-0568): the search goes to UnifAI's RAG server, the corpus the
UnifAI agents already answer from, through its bearer endpoint
``GET /api/sources/query.bearer``. The caller's own token is forwarded, so
UnifAI resolves the user and applies its own group ACL
(``metadata.acl_groups``) server-side; ``caller_groups`` is not sent. UnifAI
validates a Keycloak JWT by its JWKS and an OpenShift access token (OpenShift
Lightspeed forwards the console user's own token to the /mcp front-door,
ADR-0524) by TokenReview (UnifaiStack spec.rag.tokenReview).

``components/rag-service`` (``POST /v1/search``, keyed on the
``caller_groups`` the gateway resolved) keeps the Red Hat product
documentation, which UnifAI does not serve yet (decision of 2026-10-23 in
the WP-156 brief), so every caller gets both sources, interleaved. WP-168
migrates the documentation to UnifAI and removes rag-service from this
handler together with rag-service and rag-ingestion.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("mcp_gateway.handlers.rag_query")

UNIFAI_RAG_URL = os.getenv("UNIFAI_RAG_URL", "http://unifai-rag-server.zuno-unifai.svc:13456")
UNIFAI_RAG_TAG = os.getenv("UNIFAI_RAG_TAG", "knowledge.tech")
RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag-service.zuno-data.svc:8080")
RAG_QUERY_TIMEOUT_SECONDS = float(os.getenv("RAG_QUERY_TIMEOUT_SECONDS", "15"))

# The `technical-docs` classification (policies/data-classification/
# classification.yaml), the value rag-service reported for this domain.
_CLASSIFICATION = "C1"


def _from_unifai(match: Dict[str, Any]) -> Dict[str, Any]:
    """One UnifAI match in the result shape rag-service returned, so callers
    of the tool see no change of contract."""
    metadata = match.get("metadata") or {}
    return {
        "id": str(match.get("id", "")),
        "source": metadata.get("url") or metadata.get("path") or "",
        "title": metadata.get("title") or "",
        "snippet": match.get("content") or "",
        "score": float(match.get("score") or 0.0),
        "classification": _CLASSIFICATION,
    }


async def _search_unifai(query: str, top_k: int, bearer_token: str) -> Dict[str, Any]:
    params = {
        "query": query,
        "sourceType": "CONFLUENCE",
        "tags": UNIFAI_RAG_TAG,
        "top_k_results": top_k,
    }
    try:
        async with httpx.AsyncClient(timeout=RAG_QUERY_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{UNIFAI_RAG_URL}/api/sources/query.bearer",
                params=params,
                headers={"Authorization": f"Bearer {bearer_token}"},
            )
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPError as exc:
        logger.warning("technical-docs search call to UnifAI RAG failed: %s", exc)
        return {"error": f"technical-docs search failed: {exc}"}

    return {"results": [_from_unifai(m) for m in result.get("matches", [])]}


async def _search_rag_service(
    query: str, top_k: int, caller_sub: str, caller_groups: Optional[List[str]]
) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "query": query,
        "top_k": top_k,
        "caller_groups": caller_groups or [],
        "domains": ["knowledge.tech"],
        "caller_sub": caller_sub,
    }
    try:
        async with httpx.AsyncClient(timeout=RAG_QUERY_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{RAG_SERVICE_URL}/v1/search", json=body)
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPError as exc:
        logger.warning("technical-docs search call to rag-service failed: %s", exc)
        return {"error": f"technical-docs search failed: {exc}"}

    return {"results": result.get("results", [])}


async def handle(
    arguments: Dict[str, Any],
    caller_sub: str,
    delegated_token: Optional[str] = None,
    bearer_token: str = "",
    caller_groups: Optional[List[str]] = None,
) -> Dict[str, Any]:
    query = str(arguments.get("query", "")).strip()
    if not query:
        return {"error": "query is required"}
    top_k = int(arguments.get("top_k", 5) or 5)

    if not bearer_token:
        return await _search_rag_service(query, top_k, caller_sub, caller_groups)
    unifai, rag_service = await asyncio.gather(
        _search_unifai(query, top_k, bearer_token),
        _search_rag_service(query, top_k, caller_sub, caller_groups),
    )
    return _merge(unifai, rag_service, top_k)


def _merge(first: Dict[str, Any], second: Dict[str, Any], top_k: int) -> Dict[str, Any]:
    """Interleave two sources' results, without identical passages, capped
    at top_k. Interleaved rather than sorted: the two engines' scores are not on
    the same scale. One failed source still leaves the other's results; both
    failed reports the first error."""
    lists = [r.get("results", []) for r in (first, second) if "error" not in r]
    if not lists:
        return first
    merged: List[Dict[str, Any]] = []
    seen = set()
    for row in range(max(len(results) for results in lists)):
        for results in lists:
            if row >= len(results):
                continue
            item = results[row]
            key = (item.get("source"), item.get("snippet"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return {"results": merged[:top_k]}
