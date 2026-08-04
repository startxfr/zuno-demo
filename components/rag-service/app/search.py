"""Hybrid search: pgvector cosine similarity + PostgreSQL full-text search,
merged by reciprocal rank fusion (RRF).

ASSUMPTION (schema owned by another track — see components/rag-service
README): the `document_embeddings` table has columns
`id, source, title, content, embedding vector, metadata jsonb`, and the
`vector` extension (pgvector) is already enabled on the target database.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app import config
from app.db import get_pool
from app.embeddings import embed_query

logger = logging.getLogger("rag_service.search")

_RRF_K = 60  # standard reciprocal rank fusion smoothing constant

_VECTOR_QUERY = f"""
    SELECT id, source, title, content, metadata,
           1 - (embedding <=> $1::vector) AS score
    FROM {config.DOCUMENT_EMBEDDINGS_TABLE}
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> $1::vector
    LIMIT $2
"""

_TEXT_QUERY = f"""
    SELECT id, source, title, content, metadata,
           ts_rank_cd(
               to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content, '')),
               plainto_tsquery('english', $1)
           ) AS score
    FROM {config.DOCUMENT_EMBEDDINGS_TABLE}
    WHERE to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content, ''))
          @@ plainto_tsquery('english', $1)
    ORDER BY score DESC
    LIMIT $2
"""


def _row_to_doc(row) -> Dict[str, Any]:
    content = row["content"] or ""
    return {
        "id": str(row["id"]),
        "source": row["source"],
        "title": row["title"],
        "content": content,
        "snippet": content[:400],
        "metadata": dict(row["metadata"]) if row["metadata"] else {},
    }


async def hybrid_search(query: str, top_k: int) -> Dict[str, Any]:
    pool = get_pool()
    if pool is None:
        raise RuntimeError("database pool not initialized")

    top_k = max(1, min(top_k, config.MAX_TOP_K))
    fetch_n = max(top_k * 4, 20)  # over-fetch each ranked list before fusion

    vector_used = False
    vector_rows: List[Any] = []
    text_rows: List[Any] = []

    async with pool.acquire() as conn:
        embedding = await embed_query(query)
        if embedding is not None:
            try:
                vector_rows = await conn.fetch(_VECTOR_QUERY, embedding, fetch_n)
                vector_used = True
            except Exception as exc:
                logger.warning("pgvector similarity query failed, continuing text-only: %s", exc)
                vector_rows = []

        text_rows = await conn.fetch(_TEXT_QUERY, query, fetch_n)

    # Reciprocal rank fusion across the two ranked lists.
    fused: Dict[str, float] = {}
    docs_by_id: Dict[str, Dict[str, Any]] = {}

    for rank, row in enumerate(vector_rows, start=1):
        doc = _row_to_doc(row)
        docs_by_id[doc["id"]] = doc
        fused[doc["id"]] = fused.get(doc["id"], 0.0) + 1.0 / (_RRF_K + rank)

    for rank, row in enumerate(text_rows, start=1):
        doc = _row_to_doc(row)
        docs_by_id.setdefault(doc["id"], doc)
        fused[doc["id"]] = fused.get(doc["id"], 0.0) + 1.0 / (_RRF_K + rank)

    ranked_ids = sorted(fused.keys(), key=lambda doc_id: fused[doc_id], reverse=True)[:top_k]

    results = []
    for doc_id in ranked_ids:
        doc = docs_by_id[doc_id]
        results.append(
            {
                "id": doc["id"],
                "source": doc["source"],
                "title": doc["title"],
                "snippet": doc["snippet"],
                "score": round(fused[doc_id], 6),
            }
        )

    return {"results": results, "vector_search_used": vector_used}
