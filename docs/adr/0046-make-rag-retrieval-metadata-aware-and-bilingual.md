# ADR-0046: Make RAG retrieval metadata-aware and bilingual

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The current RAG direction combines pgvector with PostgreSQL full-text search, but Tekos requirements demand explicit product/version selection, source trust, classification, ACL handling, freshness and both French and English content. Similarity alone can return an incorrect OpenShift version even when the user names a version.

## Decision

Attach normalized metadata to every indexed chunk: product, version, language, source/source_type, classification, ACL/tenant scope where applicable, last_modified, stale_after and provenance. Apply deterministic metadata filters before ranking when the user specifies product/version or policy requires them. Support bilingual retrieval and hybrid vector/full-text ranking.

## Consequences

Tekos can answer version-specific questions more reliably and classification/ACL logic can be enforced at retrieval time.

## Security considerations

Retrieval must never return documents the user cannot access. C2/C3 metadata must propagate into effective classification according to ADR-0034.

## Operational considerations

Add test corpora containing conflicting versions and bilingual content; acceptance tests must prove the requested version is preferred or enforced.

## Implementation state

**Implemented (2026-08-05).**

- Every field the Decision names lives inside `document_embeddings`'s existing `metadata jsonb` column rather than as new typed columns - `data/rag/schema/003_rag_metadata.sql` documents the convention (`product`, `version`, `language`, `source_type`, `classification`, `acl_groups`, `last_modified`, `stale_after`, `provenance`) and adds expression indexes on the fields used as hot-path filters. Tenant scope is not applicable (single-tenant demo); `acl_groups` is implemented and enforced (see Security below). `data/rag/fixtures/seed.sql` is a new fictional demo corpus (`data/rag/` was previously an empty stub), seeded by a new `ansible/roles/rag` task using the same one-shot-Job pattern as `ansible/roles/sql_schema`.
- Deterministic filters and bilingual ranking: `components/rag-service/app/search.py`'s `_filter_clause` applies exact-match `product`/`version` predicates to both the vector and full-text candidate queries before `LIMIT`, only when supplied - `components/agent-runtime/app/graph/nodes.py`'s new `_extract_product_version` regex (tested in `test_retrieve_metadata.py`) resolves "OpenShift AI 3.5"-style question text into that filter. `language` is a soft rank boost, not a hard filter (a small demo corpus can have zero matches in one language); bilingual full-text comes from a new generated `content_tsv` column whose text-search configuration is chosen per row from `metadata.language` (the previous hardcoded `to_tsvector('english', ...)` could never match French content). `stale_after` applies a rank penalty rather than excluding a result, and is surfaced in the model's own context block so it can prefer the right source.
- Security/verification: ACL enforcement (`_filter_clause`'s jsonb `?|` predicate) is mandatory, not conditional - an empty `caller_groups` excludes every ACL-restricted document (fail closed). Verified against a real PostgreSQL 16 + pgvector instance: version filter excludes the wrong version, empty `caller_groups` excludes the ACL-restricted doc while `["consultant"]` includes it, a French-boosted query ranks the French document first, a stale document is down-ranked but still returned, and `POST /v1/search` over real HTTP returns the same result. This surfaced and fixed a genuine, previously-latent bug: `app/db.py`'s asyncpg pool never registered a `jsonb` type codec, so `metadata` came back as a raw JSON string and `_row_to_doc`'s `dict(row["metadata"])` call would have raised `ValueError` on the first real request against a live database - fixed by registering a `jsonb` codec on the pool's `init` callback. Classification propagation into `effective_classification` (ADR-0034) is implemented in `retrieve_node`: the highest classification among retrieved docs now escalates the turn's classification, same as `tool_call_node` already did for Confluence - confirmed live (`caller_groups=["board"]` against the roadmap query returned `classification: "C2"`).
- Test corpora: `data/rag/fixtures/seed.sql` has two conflicting-version document pairs (GPU sizing and ServingRuntime config, OpenShift AI 2.16 vs. 3.5) and an EN/FR pair; enforcement is proven by `components/agent-runtime/tests/test_retrieve_metadata.py` (the extraction driving the filter) and `components/rag-service/tests/test_search_filters.py` (the filter clause itself), both passing without a live database.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.

## Related ADRs

- ADR-0015
- ADR-0109
- ADR-0110
- ADR-0034
- ADR-0035
