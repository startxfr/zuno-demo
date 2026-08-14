"""OpenAI-compatible embedding client.

Assumes an embedding model is served behind an OpenAI-compatible
`POST /v1/embeddings` endpoint (a KServe/vLLM `InferenceService`, or any
other OpenAI-compatible embedding runtime) -- see `EMBEDDING_SERVICE_URL`
in app/config.py. Independent of the OGX Operator (ADR-0322, supersedes
ADR-0018 for OGX product mapping) - see app/ogx_provider.py for that
separate, optional retrieval provider. This is a best-effort dependency:
if it is unreachable, `search.py` falls back to full-text-search only
rather than failing the whole request.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import httpx

from app import config

logger = logging.getLogger("rag_service.embeddings")


class EmbeddingUnavailable(Exception):
    pass


async def embed_query(text: str) -> Optional[List[float]]:
    payload = {"model": config.EMBEDDING_MODEL_NAME, "input": [text]}
    try:
        async with httpx.AsyncClient(timeout=config.EMBEDDING_TIMEOUT_SECONDS) as client:
            resp = await client.post(config.EMBEDDING_SERVICE_URL, json=payload)
        resp.raise_for_status()
        body = resp.json()
        return body["data"][0]["embedding"]
    except Exception as exc:
        logger.warning(
            "embedding service unavailable at %s (%s); hybrid search will fall back to full-text only",
            config.EMBEDDING_SERVICE_URL,
            exc,
        )
        return None
