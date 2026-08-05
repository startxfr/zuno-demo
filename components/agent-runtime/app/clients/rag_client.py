"""Client for the RAG service (components/rag-service), used by the
`retrieve` graph node.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag-service.zuno-data.svc:8080")
RAG_TIMEOUT_SECONDS = float(os.getenv("RAG_TIMEOUT_SECONDS", "15"))


class RagClientError(Exception):
    pass


async def search(
    query: str,
    top_k: int = 5,
    product: Optional[str] = None,
    version: Optional[str] = None,
    language: Optional[str] = None,
    caller_groups: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """ADR-0046: product/version are deterministic pre-ranking filters
    (set by app/graph/nodes.py:_extract_product_version when the user's
    question names one), language is a soft ranking preference, and
    caller_groups is forwarded so rag-service can enforce ACL-restricted
    documents server-side (fail closed - see that service's own
    app/search.py) rather than this client trusting the response already
    excluded everything the caller can't see.
    """
    body: Dict[str, Any] = {"query": query, "top_k": top_k, "caller_groups": caller_groups or []}
    if product:
        body["product"] = product
    if version:
        body["version"] = version
    if language:
        body["language"] = language

    try:
        async with httpx.AsyncClient(timeout=RAG_TIMEOUT_SECONDS) as client:
            resp = await client.post(f"{RAG_SERVICE_URL}/v1/search", json=body)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise RagClientError(str(exc)) from exc
    body = resp.json()
    return body.get("results", [])
