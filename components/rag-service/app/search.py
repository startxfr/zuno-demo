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
from app.telemetry import record_freshness_lag

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
# the result rather than this service silently hiding it. This is the
# floor of _freshness_decay_factor's continuous decay below (WP-24) and
# also the fallback used when a stale doc's own metadata doesn't carry a
# parseable stale_after to grade severity from - unchanged value/meaning
# from the original binary penalty, tests/test_search_filters.py depends
# on the exact constant.
_STALE_PENALTY_FACTOR = 0.5

# ADR-0205/WP-24: once a doc has been stale for this many days, freshness
# decay bottoms out - never fully zeroed (a very old source may still be
# the only answer), but never ranked as if it just barely missed its
# staleness window either. Chosen as a full quarter: distinguishing "just
# went stale" from "extremely old" only matters over that kind of horizon
# for this corpus's freshness objectives (weekly..on-demand, see
# knowledge/*/domain.yaml).
_FRESHNESS_DECAY_FLOOR = 0.15
_FRESHNESS_DECAY_FULL_DAYS = 90

# ADR-0205: a chunk whose provenance is a real, independently-checkable
# URL is a stronger citation than one carrying only a synthetic/fixture
# marker (ADR-0025) - a light weight, not a hard filter, since fixture
# content is still legitimate corpus content for this demo.
_PROVENANCE_URL_WEIGHT = 1.0
_PROVENANCE_UNVERIFIABLE_WEIGHT = 0.95

# ADR-0205/WP-24: a chunk in an operational (non-immutable-legacy) domain
# that carries neither `indexed_at` nor `stale_after` predates this WP's
# metadata enforcement (components/rag-ingestion's validate stage now
# requires both on every new/changed operational chunk) - trust scoring
# treats it the same way ADR-0202/ADR-0203 treat an untrusted
# classification: never silently trust it, down-rank hard and flag it
# (`freshness_untrusted: true`) rather than either dropping it or ranking
# it as if its freshness were known. `knowledge.sxa-legacy` is the one
# domain WP-22/ADR-0206 declared exempt (a point-in-time dump snapshot,
# not a continuously-refreshed operational source).
_IMMUTABLE_LEGACY_DOMAINS = {"knowledge.sxa-legacy"}
_FRESHNESS_UNTRUSTED_PENALTY_FACTOR = 0.05


def _provenance_weight(metadata: Dict[str, Any]) -> float:
    provenance = metadata.get("provenance")
    if not provenance:
        # No provenance recorded at all is a different, non-penalized case
        # from a provenance value that IS present but isn't a URL (a known
        # fixture/synthetic marker, ADR-0025) - only the latter is a known
        # weaker citation. Also the no-op every caller that never sets
        # `metadata` at all (this repo's synthetic ranking-unit-test docs)
        # gets, by construction (`metadata or {}` upstream -> `{}` -> no
        # provenance key -> here).
        return _PROVENANCE_URL_WEIGHT
    if isinstance(provenance, str) and provenance.startswith(("http://", "https://")):
        return _PROVENANCE_URL_WEIGHT
    return _PROVENANCE_UNVERIFIABLE_WEIGHT


def _freshness_decay_factor(is_stale: bool, metadata: Optional[Dict[str, Any]]) -> float:
    """Continuous decay once a doc is stale, replacing the previous flat
    penalty with one that sinks progressively staler content further -
    never below `_FRESHNESS_DECAY_FLOOR`, never exclusionary. Falls back
    to the original flat `_STALE_PENALTY_FACTOR` when there is no
    `metadata` dict at all, or no parseable `stale_after` to grade
    severity from (a doc can be known-stale via `_is_stale` without this
    function being able to say how stale) - this fallback is also what
    keeps this function's output identical to the pre-WP-24 behavior for
    every existing caller that never passes a metadata dict."""
    if not is_stale:
        return 1.0
    stale_after = (metadata or {}).get("stale_after")
    if not stale_after:
        return _STALE_PENALTY_FACTOR
    parsed = _parse_stale_after(stale_after)
    if parsed is None:
        return _STALE_PENALTY_FACTOR
    days_stale = (_dt.datetime.now(_dt.timezone.utc) - parsed).days
    if days_stale <= 0:
        return _STALE_PENALTY_FACTOR
    fraction = min(days_stale / _FRESHNESS_DECAY_FULL_DAYS, 1.0)
    return _STALE_PENALTY_FACTOR - (_STALE_PENALTY_FACTOR - _FRESHNESS_DECAY_FLOOR) * fraction


def _is_freshness_untrusted(domain: str, metadata: Dict[str, Any]) -> bool:
    if domain in _IMMUTABLE_LEGACY_DOMAINS:
        return False
    return not metadata.get("indexed_at") and not metadata.get("stale_after")


def _record_freshness_lag(doc: Dict[str, Any]) -> None:
    """ADR-0109/WP-24 lag metric: only for chunks actually returned to a
    caller (post-ranking/truncation) - recording it for every over-fetched
    candidate row would skew the histogram with results nobody saw."""
    indexed_at = (doc.get("metadata") or {}).get("indexed_at")
    if not indexed_at:
        return
    parsed = _parse_stale_after(indexed_at)  # same generic ISO datetime parser
    if parsed is None:
        return
    lag_seconds = (_dt.datetime.now(_dt.timezone.utc) - parsed).total_seconds()
    record_freshness_lag(doc["domain"], max(lag_seconds, 0.0))


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


def _parse_stale_after(stale_after: str) -> Optional[_dt.datetime]:
    """ADR-0205/WP-24: stale_after must support sub-day granularity (the
    sales domain's hours-scale freshness objective, knowledge/sales/
    domain.yaml) - datetime.fromisoformat (Python 3.11+) parses both a
    bare date (e.g. "2027-01-01", the pre-WP-24 fixture convention -
    treated as midnight) and a full ISO datetime with an offset/"Z"
    suffix, so this stays backward compatible with every value written
    before this WP without a migration."""
    try:
        parsed = _dt.datetime.fromisoformat(stale_after)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed


def _is_stale(metadata: Dict[str, Any]) -> bool:
    stale_after = metadata.get("stale_after")
    if not stale_after:
        return False
    parsed = _parse_stale_after(stale_after)
    if parsed is None:
        logger.warning("metadata.stale_after=%r is not an ISO date/datetime, ignoring", stale_after)
        return False
    return parsed < _dt.datetime.now(_dt.timezone.utc)


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
        # ADR-0205/WP-24: computed from the real metadata dict here (not in
        # _apply_soft_adjustments) so a caller building `doc` any other way
        # (there is exactly one: the synthetic fixtures in
        # tests/test_search_filters.py) never has this key at all, which is
        # exactly the "we don't know" signal _apply_soft_adjustments' fallback
        # relies on to stay backward compatible.
        "freshness_untrusted": _is_freshness_untrusted(metadata.get("domain", "knowledge.tech"), metadata),
    }


def _apply_soft_adjustments(fused: Dict[str, float], docs_by_id: Dict[str, Dict[str, Any]], language: Optional[str]) -> None:
    """Applies ADR-0046's soft language preference plus ADR-0205/WP-24's
    trust scoring (provenance weight, freshness decay, freshness-untrusted
    penalty) in place, after fusion so both ranked lists' contributions
    are already combined before any adjustment. A standalone function so
    tests/test_search_filters.py can exercise the ranking behavior with
    synthetic docs, without a real database - every WP-24 addition below
    reads from keys (`metadata`, `freshness_untrusted`) that
    app/search.py:_row_to_doc always sets on a real result but a minimal
    synthetic test doc need not, and each falls back to a no-op (weight
    1.0 / flat _STALE_PENALTY_FACTOR / not untrusted) when absent -
    exactly the pre-WP-24 behavior, so older tests keep their exact
    expected values.
    """
    for doc_id, doc in docs_by_id.items():
        if language and doc["language"] == language:
            fused[doc_id] += _LANGUAGE_BOOST
        metadata = doc.get("metadata")
        fused[doc_id] *= _provenance_weight(metadata or {})
        fused[doc_id] *= _freshness_decay_factor(doc["stale"], metadata)
        if doc.get("freshness_untrusted"):
            fused[doc_id] *= _FRESHNESS_UNTRUSTED_PENALTY_FACTOR


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
    """ADR-0204 (WP-21): domains selects which per-domain database pool(s)
    (app/bindings.py's KnowledgeBindingRegistry, app/db.py's pool registry)
    to fan out to and merge results from - never "all pools", since that
    would silently include content the caller was never authorized for
    (Agent Runtime's app/knowledge.py:evaluate_knowledge() already computed
    the authorized set; this is defense in depth around it, not a second
    opinion). An absent/empty domains list defaults to knowledge.tech only
    - the sole domain this service ever served before ADR-0204, preserving
    every pre-existing caller's behavior unchanged.

    A domain with no live pool (down, or its ExternalSecret not yet
    populated) fails the whole call (RuntimeError) rather than silently
    returning partial results from whichever domains happen to be up -
    "no silent partial results" applies to domain availability the same
    way ADR-0205 later applies it to freshness/source substitution.
    """
    caller_groups = caller_groups or []
    effective_domains = list(domains) if domains else ["knowledge.tech"]
    top_k = max(1, min(top_k, config.MAX_TOP_K))
    fetch_n = max(top_k * 4, 20)  # over-fetch each ranked list before fusion

    filter_sql, filter_params = _filter_clause(3, product, version, caller_groups, effective_domains, technology)

    vector_used = False
    fused: Dict[str, float] = {}
    docs_by_id: Dict[str, Dict[str, Any]] = {}

    def _accumulate(rows: List[Any]) -> None:
        # Ranked WITHIN this one source list (a single domain's vector or
        # text results) - standard multi-list RRF fuses contributions from
        # each source's own rank position, never a position in some
        # concatenation of multiple domains' result sets (which would
        # unfairly penalize every domain queried after the first).
        for rank, row in enumerate(rows, start=1):
            doc = _row_to_doc(row)
            docs_by_id.setdefault(doc["id"], doc)
            fused[doc["id"]] = fused.get(doc["id"], 0.0) + 1.0 / (_RRF_K + rank)

    embedding = await embed_query(query)

    for domain in effective_domains:
        pool = get_pool(domain)
        if pool is None:
            # "No silent partial results": a caller asking for N domains
            # gets either all N or a clear failure, never a quietly
            # incomplete answer that looks the same as "nothing matched" -
            # the same posture the pre-ADR-0204 single pool already had
            # (it simply had nothing to be partial about).
            raise RuntimeError(f"no live database pool for requested domain '{domain}'")

        async with pool.acquire() as conn:
            if embedding is not None:
                try:
                    domain_vector_rows = await conn.fetch(_vector_query(filter_sql), embedding, fetch_n, *filter_params)
                    _accumulate(domain_vector_rows)
                    vector_used = True
                except Exception as exc:
                    logger.warning("pgvector similarity query failed for domain '%s', continuing text-only: %s", domain, exc)

            domain_text_rows = await conn.fetch(_text_query(filter_sql), query, fetch_n, *filter_params)
            _accumulate(domain_text_rows)

    _apply_soft_adjustments(fused, docs_by_id, language)

    ranked_ids = sorted(fused.keys(), key=lambda doc_id: fused[doc_id], reverse=True)[:top_k]

    results = []
    for doc_id in ranked_ids:
        doc = docs_by_id[doc_id]
        _record_freshness_lag(doc)
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
                "freshness_untrusted": doc["freshness_untrusted"],
            }
        )

    return {"results": results, "vector_search_used": vector_used}
