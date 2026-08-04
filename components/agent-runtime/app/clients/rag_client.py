"""Client for the RAG service (components/rag-service), used by the
`retrieve` graph node.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx

RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag-service.zuno-data.svc:8080")
RAG_TIMEOUT_SECONDS = float(os.getenv("RAG_TIMEOUT_SECONDS", "15"))


class RagClientError(Exception):
    pass


async def search(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=RAG_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{RAG_SERVICE_URL}/v1/search", json={"query": query, "top_k": top_k}
            )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise RagClientError(str(exc)) from exc
    body = resp.json()
    return body.get("results", [])
