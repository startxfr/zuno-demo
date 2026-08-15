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
    domains: Optional[List[str]] = None,
    technology: Optional[str] = None,
    project_id: Optional[str] = None,
    caller_sub: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """ADR-0046: product/version are deterministic pre-ranking filters
    (set by app/graph/nodes.py:_extract_product_version when the user's
    question names one), language is a soft ranking preference, and
    caller_groups is forwarded so rag-service can enforce ACL-restricted
    documents server-side (fail closed - see that service's own
    app/search.py) rather than this client trusting the response already
    excluded everything the caller can't see.

    ADR-0203: domains is the set of knowledge domains
    app/knowledge.py:evaluate_knowledge() already authorized for this call -
    rag-service applies it as defense in depth (its own filter, on top of
    the authorization decision already made here); never sent empty when a
    domain-aware call is intended, since an absent/empty list means "no
    domain filtering" server-side (ADR-0202 acceptance: one canonical
    `technology` filters web + Confluence chunks - a hard filter like
    product/version, forwarded the same way).
    """
    body: Dict[str, Any] = {"query": query, "top_k": top_k, "caller_groups": caller_groups or []}
    if product:
        body["product"] = product
    if version:
        body["version"] = version
    if language:
        body["language"] = language
    if domains:
        body["domains"] = domains
    if technology:
        body["technology"] = technology
    # ADR-0209: required by rag-service whenever knowledge.project is
    # among `domains` - a fail-closed membership check needs both to know
    # WHICH project and WHO is asking. Sent whenever present regardless
    # of whether knowledge.project is actually requested this call: it's
    # inert if knowledge.project isn't in `domains`, and this keeps the
    # forwarding logic here simple (no need to special-case).
    if project_id:
        body["project_id"] = project_id
    if caller_sub:
        body["caller_sub"] = caller_sub

    try:
        async with httpx.AsyncClient(timeout=RAG_TIMEOUT_SECONDS) as client:
            resp = await client.post(f"{RAG_SERVICE_URL}/v1/search", json=body)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise RagClientError(str(exc)) from exc
    body = resp.json()
    return body.get("results", [])
