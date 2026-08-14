"""Hybrid search: pgvector cosine similarity + PostgreSQL full-text search,
merged by reciprocal rank fusion (RRF), with ADR-0046's deterministic
metadata filters, ACL enforcement, bilingual ranking and staleness
penalty layered on top.

ASSUMPTION (schema owned by another track - see components/rag-service
README): the `document_embeddings` table has columns
`id, source, title, content, embedding vector, metadata jsonb,
content_tsv tsvector` (the last added by data/rag/schema/003_rag_metadata.sql,
ADR-0046), and the `vector` extension (pgvector) is already enabled on the
target database.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Dict, List, Optional, Tuple

from app import config
from app.db import get_pool
from app.embeddings import embed_query

logger = logging.getLogger("rag_service.search")

_RRF_K = 60  # standard reciprocal rank fusion smoothing constant

# ADR-0046: `language` is a soft preference (a rank boost), not a hard
# filter like product/version - a small bilingual demo corpus can easily
# have zero matches in one language for a given query, and silently
# returning nothing would be worse than returning the best available
# result in the "wrong" language. RRF's per-list contributions are on the
# order of 1/(60+rank) (~0.016 at rank 1, smaller thereafter), so a 0.01
# boost is enough to reorder near-ties without overwhelming genuine
# relevance signal from the vector/text ranks themselves.
_LANGUAGE_BOOST = 0.01

# A stale document (metadata.stale_after in the past) is down-ranked, not
# excluded outright - it may still be the only source for a question, and
# the caller (Agent Runtime) can decide what to do with `stale: true` on
# the result rather than this service silently hiding it.
_STALE_PENALTY_FACTOR = 0.5


def _filter_clause(
    start_index: int,
    product: Optional[str],
    version: Optional[str],
    caller_groups: List[str],
    domains: Optional[List[str]] = None,
    technology: Optional[str] = None,
) -> Tuple[str, List[Any]]:
    """Builds an " AND ..." SQL fragment applied identically to both the
    vector and full-text candidate queries: ADR-0046's deterministic
    product/version filters when the caller supplied them, plus mandatory
    ACL enforcement (ADR-0046 Security considerations: "Retrieval must
    never return documents the user cannot access") - always applied, even
    when caller_groups is empty, so an ACL-restricted document with no
    matching caller group is never returned (fail closed, not fail open).
    Every value is a bound asyncpg positional parameter, never
    string-interpolated - the SQL text itself contains no caller input.

    ADR-0203: domains is defense in depth - the caller (Agent Runtime) has
    already evaluated the full knowledge-domain policy intersection and
    sends only what it authorized. Additive/optional: an empty/absent list
    applies no domain clause at all (pre-ADR-0202 rows carry no `domain`
    metadata key; once a caller does send domains, such untagged rows are
    treated as knowledge.tech - the same default app/schemas.py:SearchResult
    and _row_to_doc below use, so a domain-scoped query still sees legacy
    tech content instead of silently losing it).

    ADR-0202: technology is a hard filter (like product/version), not a
    ranking preference - the one canonical cross-source key that lets a
    query combine official web documentation and Confluence chunks.
    """
    clauses = []
    params: List[Any] = []
    idx = start_index

    if product:
        clauses.append(f"metadata ->> 'product' = ${idx}")
        params.append(product)
        idx += 1
    if version:
        clauses.append(f"metadata ->> 'version' = ${idx}")
        params.append(version)
        idx += 1
    if technology:
        clauses.append(f"metadata ->> 'technology' = ${idx}")
        params.append(technology)
        idx += 1
    if domains:
        clauses.append(
            f"((metadata ? 'domain' AND metadata ->> 'domain' = ANY(${idx}::text[])) "
            f"OR (NOT (metadata ? 'domain') AND 'knowledge.tech' = ANY(${idx}::text[])))"
        )
        params.append(domains)
        idx += 1

    # A document with no acl_groups key, an empty array, or a null value is
    # unrestricted; jsonb `?|` tests whether any element of the given
    # text[] exists as a top-level element of the left-hand jsonb array.
    clauses.append(
        "(NOT (metadata ? 'acl_groups') OR jsonb_array_length(metadata -> 'acl_groups') = 0 "
        f"OR (metadata -> 'acl_groups') ?| ${idx}::text[])"
    )
    params.append(caller_groups)

    return " AND " + " AND ".join(clauses), params


def _vector_query(filter_sql: str) -> str:
    return f"""
        SELECT id, source, title, content, metadata,
               1 - (embedding <=> $1::vector) AS score
        FROM {config.DOCUMENT_EMBEDDINGS_TABLE}
        WHERE embedding IS NOT NULL{filter_sql}
        ORDER BY embedding <=> $1::vector
        LIMIT $2
    """


def _text_query(filter_sql: str) -> str:
    # Bilingual (ADR-0046): content_tsv (data/rag/schema/003_rag_metadata.sql)
    # is generated per-row using the row's own metadata.language for its
    # text-search configuration; the query side matches against an
    # English-or-French tsquery OR'd together rather than requiring the
    # caller to know the row's language up front.
    return f"""
        SELECT id, source, title, content, metadata,
               ts_rank_cd(content_tsv, plainto_tsquery('english', $1) || plainto_tsquery('french', $1)) AS score
        FROM {config.DOCUMENT_EMBEDDINGS_TABLE}
        WHERE content_tsv @@ (plainto_tsquery('english', $1) || plainto_tsquery('french', $1)){filter_sql}
        ORDER BY score DESC
        LIMIT $2
    """


def _is_stale(metadata: Dict[str, Any]) -> bool:
    stale_after = metadata.get("stale_after")
    if not stale_after:
        return False
    try:
        return _dt.date.fromisoformat(stale_after) < _dt.date.today()
    except ValueError:
        logger.warning("metadata.stale_after=%r is not an ISO date, ignoring", stale_after)
        return False


def _row_to_doc(row) -> Dict[str, Any]:
    content = row["content"] or ""
    metadata = dict(row["metadata"]) if row["metadata"] else {}
    return {
        "id": str(row["id"]),
        "source": row["source"],
        "title": row["title"],
        "content": content,
        "snippet": content[:400],
        "metadata": metadata,
        # ADR-0034/0046: a document with no classification tag defaults to
        # C1 (public-or-internal-low-risk), the same baseline
        # app/graph/nodes.py:retrieve_node used unconditionally before this
        # ADR - never invent a higher-than-declared classification, but
        # also never silently treat an untagged legacy row as unclassified.
        "classification": metadata.get("classification", "C1"),
        "language": metadata.get("language"),
        "product": metadata.get("product"),
        "version": metadata.get("version"),
        "stale": _is_stale(metadata),
        # ADR-0202: untagged legacy rows default to knowledge.tech - the
        # same convention _filter_clause's domain clause above uses, so a
        # domain-scoped query and this default never disagree about what a
        # tagless row belongs to.
        "domain": metadata.get("domain", "knowledge.tech"),
    }


def _apply_soft_adjustments(fused: Dict[str, float], docs_by_id: Dict[str, Dict[str, Any]], language: Optional[str]) -> None:
    """Applies ADR-0046's soft language preference and staleness penalty
    in place, after fusion so both ranked lists' contributions are already
    combined before either adjustment. A standalone function so
    tests/test_search_filters.py can exercise the ranking behavior with
    synthetic docs, without a real database.
    """
    for doc_id, doc in docs_by_id.items():
        if language and doc["language"] == language:
            fused[doc_id] += _LANGUAGE_BOOST
        if doc["stale"]:
            fused[doc_id] *= _STALE_PENALTY_FACTOR


async def hybrid_search(
    query: str,
    top_k: int,
    product: Optional[str] = None,
    version: Optional[str] = None,
    language: Optional[str] = None,
    caller_groups: Optional[List[str]] = None,
    domains: Optional[List[str]] = None,
    technology: Optional[str] = None,
) -> Dict[str, Any]:
    pool = get_pool()
    if pool is None:
        raise RuntimeError("database pool not initialized")

    caller_groups = caller_groups or []
    top_k = max(1, min(top_k, config.MAX_TOP_K))
    fetch_n = max(top_k * 4, 20)  # over-fetch each ranked list before fusion

    filter_sql, filter_params = _filter_clause(3, product, version, caller_groups, domains, technology)

    vector_used = False
    vector_rows: List[Any] = []
    text_rows: List[Any] = []

    async with pool.acquire() as conn:
        embedding = await embed_query(query)
        if embedding is not None:
            try:
                vector_rows = await conn.fetch(_vector_query(filter_sql), embedding, fetch_n, *filter_params)
                vector_used = True
            except Exception as exc:
                logger.warning("pgvector similarity query failed, continuing text-only: %s", exc)
                vector_rows = []

        text_rows = await conn.fetch(_text_query(filter_sql), query, fetch_n, *filter_params)

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

    _apply_soft_adjustments(fused, docs_by_id, language)

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
                "classification": doc["classification"],
                "language": doc["language"],
                "product": doc["product"],
                "version": doc["version"],
                "stale": doc["stale"],
                "domain": doc["domain"],
            }
        )

    return {"results": results, "vector_search_used": vector_used}
