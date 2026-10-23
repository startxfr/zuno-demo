"""In-process handler for the ``search_technical_docs`` MCP tool
(capability ``knowledge.tech.search``).

WP-156 (ADR-0568): the search goes to UnifAI's RAG server, the corpus the
UnifAI agents already answer from, through its bearer endpoint
``GET /api/sources/query.bearer``. The caller's own Keycloak access token is
forwarded, so UnifAI resolves the user and applies its own group ACL
(``metadata.acl_groups``) server-side; ``caller_groups`` is not sent.

An OpenShift access token (OpenShift Lightspeed forwards the console user's
own token to the /mcp front-door, ADR-0524) is answered by
``components/rag-service`` (``POST /v1/search``), keyed on the
``caller_groups`` the gateway's TokenReview resolved. rag-service keeps the
Red Hat product documentation, which UnifAI does not serve yet (decision of
2026-10-23 in the WP-156 brief); WP-168 migrates it to UnifAI and removes
this branch together with rag-service and rag-ingestion.
"""

from __future__ import annotations

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


def _is_keycloak_jwt(token: str) -> bool:
    """Same test as app/auth.py's _looks_like_jwt: three dot-separated
    segments, never an OpenShift `sha256~` token."""
    return token.count(".") == 2 and not token.startswith("sha256~")


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

    if bearer_token and _is_keycloak_jwt(bearer_token):
        return await _search_unifai(query, top_k, bearer_token)
    return await _search_rag_service(query, top_k, caller_sub, caller_groups)
