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

Two source types answer: ``CONFLUENCE`` (the private wiki spaces, filtered by
the caller's groups) and ``WEB`` (the public Red Hat product documentation,
visible to every signed-in user; WP-168). Both are queried for the
``knowledge.tech`` tag and interleaved.
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
SOURCE_TYPES = [t for t in os.getenv("UNIFAI_RAG_SOURCE_TYPES", "CONFLUENCE,WEB").split(",") if t]
RAG_QUERY_TIMEOUT_SECONDS = float(os.getenv("RAG_QUERY_TIMEOUT_SECONDS", "15"))

# WP-187 (ADR-0568): each chunk carries its source's classification in its
# metadata (UnifaiRAGSource spec.classification, UnifAI operator 0.1.50). A
# chunk without one, or with a value outside the four levels, is returned as C2: fail
# closed, user decision 2026-11-02. The label is for audit and for callers that
# raise their own level; the external-model block is the routing policy's
# local_only_for, not this field.
_CLASSIFICATIONS = tuple(f"C{level}" for level in range(1, 5))
_CLASSIFICATION_WHEN_MISSING = "C2"


def _classification(metadata: Dict[str, Any]) -> str:
    value = str(metadata.get("classification") or "").strip().upper()
    return value if value in _CLASSIFICATIONS else _CLASSIFICATION_WHEN_MISSING


def _from_unifai(match: Dict[str, Any]) -> Dict[str, Any]:
    """One UnifAI match in the result shape the retired rag-service returned, so callers
    of the tool see no change of contract."""
    metadata = match.get("metadata") or {}
    return {
        "id": str(match.get("id", "")),
        "source": metadata.get("url") or metadata.get("path") or "",
        "title": metadata.get("title") or "",
        "snippet": match.get("content") or "",
        "score": float(match.get("score") or 0.0),
        "classification": _classification(metadata),
    }


MAX_TOP_K = 20


async def _search_unifai(query: str, top_k: int, bearer_token: str, source_type: str) -> Dict[str, Any]:
    params = {
        "query": query,
        "sourceType": source_type,
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
        logger.warning("technical-docs search call to UnifAI RAG (%s) failed: %s", source_type, exc)
        return {"error": f"technical-docs search failed: {exc}"}

    return {"results": [_from_unifai(m) for m in result.get("matches", [])]}


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
    # ADR-0603 / WP-222: top_k is model-chosen; without a ceiling one call can
    # ask UnifAI for any number of passages per source type.
    try:
        top_k = int(arguments.get("top_k", 5) or 5)
    except (TypeError, ValueError):
        top_k = 5  # a non-numeric value from the model falls back to the default
    top_k = max(1, min(top_k, MAX_TOP_K))

    if not bearer_token:
        return {"error": "technical-docs search needs the caller's bearer token"}
    responses = await asyncio.gather(*(_search_unifai(query, top_k, bearer_token, t) for t in SOURCE_TYPES))
    return _merge(responses, top_k)


def _merge(responses: List[Dict[str, Any]], top_k: int) -> Dict[str, Any]:
    """Interleave the source types' results, without identical passages, capped
    at top_k. Interleaved rather than sorted: the scores of two collections are
    not on the same scale. One failed source type still leaves the others'
    results; all failed reports the first error."""
    lists = [r.get("results", []) for r in responses if "error" not in r]
    if not lists:
        return responses[0]
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
