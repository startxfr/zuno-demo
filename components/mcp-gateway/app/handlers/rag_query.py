"""In-process handler for the ``search_technical_docs`` MCP tool
(capability ``knowledge.tech.search``).

Calls the platform's real, already-deployed ``components/rag-service``
(``POST /v1/search``) over the ``knowledge.tech`` domain - the same
``rag-tech`` pgvector corpus Tekos's agent-runtime already queries via
``components/agent-runtime/app/clients/rag_client.py``. No new backend: this
is a thin proxy, same shape as ``image_gen.py``'s call to ai-gateway.

ACL enforcement happens server-side in rag-service (``app/search.py``'s
``_filter_clause``, fail-closed on ``metadata.acl_groups``), keyed on
``caller_groups`` - not on a bearer token, since rag-service has no
token-validation of its own. That is why this handler, unlike every other
one in this package, actually needs the ``caller_groups`` kwarg
``app/downstream.py`` threads through from the caller's reviewed identity.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("mcp_gateway.handlers.rag_query")

RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag-service.zuno-data.svc:8080")
RAG_QUERY_TIMEOUT_SECONDS = float(os.getenv("RAG_QUERY_TIMEOUT_SECONDS", "15"))


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
