# ADR-0206: Separate current Salesforce knowledge from legacy SXA

- **Status:** Implemented (retrieval-only, per ADR-0219 — see Status update below)
- **Target:** v0.6 (retargeted from v0.7 on 2026-08-30 — v0.7 split into a short-term closeout band (v0.6) and a long-term/harder band (v0.7); this item and its already-closed siblings ADR-0105/ADR-0213/ADR-0218 move to v0.6, while ADR-0111/ADR-0115 (externally blocked) and ADR-0352 (large not-started effort) remain in v0.7. Previously retargeted from v0.2 on 2026-08-26 — roadmap reprioritization, grouped into v0.7 alongside ADR-0105)
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team

## Context

The repository already migrates the historical SXA SQL schema into PostgreSQL and exposes controlled sales-data tools. The target information architecture now establishes Salesforce as the current commercial system while retaining SXA only as historical knowledge for Sales and Direction.

Mixing Salesforce and SXA rows in one undifferentiated `sales` corpus would blur authority, freshness and lineage. Conversely, vectorizing the legacy dump alone would lose the precision of structured SQL for exact counts/aggregations and schema exploration.

## Status update (2026-08-26)

[ADR-0219](0219-serve-sxa-only-as-a-historical-rag-corpus.md) withdraws the
deterministic half of this ADR's two-way SXA access model. SXA is the
company's closed pre-2021 record, so there is no live store for exact
structured queries to be authoritative against: the five `sxa.*`
capabilities and the `sales-db` MCP server behind them are deleted, and
legacy SXA is reachable through `knowledge.sxa-legacy` retrieval only.

The separation this ADR exists for is unchanged and still enforced: current
Salesforce knowledge and legacy SXA knowledge never serve each other's
content, in either direction, and the `sales.*` capability namespace stays
reserved for a real live-Salesforce server. ADR-0219 also widened
`knowledge.sxa-legacy`'s `allowed_groups` to `[sales, board, adv, finance]`,
absorbing what the retired `knowledge.sxa` domain had granted.

## Status update (2026-08-30)

**Live snapshot load: complete, via a different path than planned.** This
ADR's original acceptance criterion ("exact aggregations can use
deterministic structured-query capabilities without arbitrary SQL
execution") is now void, not merely pending: ADR-0219 permanently retired
that whole path (the MariaDB `sxa` database, the `sales-db` MCP server, the
`sxa.*` capabilities) — there is nothing left for a live snapshot to feed on
that side. WP-23's live-load action was reassigned to WP-065, which was
itself abandoned for the same reason on 2026-08-26. The load that actually
matters — real content into `knowledge.sxa-legacy`'s retrieval path — was
completed and verified by WP-084 on 2026-08-27: 319,713 chunk rows across
310,398 distinct real SXA sources indexed into `rag-sxa-legacy`, retrieval
confirmed live against `rag-service`'s `/v1/search` with a real corpus
query. No replacement for exact-figure structured queries exists or is
planned outside a possible future live-Salesforce `sales.*` server.

**Classification lowered C3 → C2.** `knowledge.sxa-legacy` is an immutable
historical snapshot with no live system and no write path behind it —
exactly why it is served through RAG directly rather than through an MCP
surface onto a structured database, and why it is treated as one
undifferentiated historical corpus rather than field-by-field. On that
basis, the domain is reclassified from C3 ("local-model-only") to C2
("business-sensitive", restricted-SaaS-eligible), the same tier as
`sales-data` in `policies/data-classification/classification.yaml`. This
decision is made at the domain level, directly, and **closes** the
field-level data review this ADR's Decision text and WP-23 deferred — no
further granular per-table/column review is scheduled. It changes what is
*eligible* for restricted SaaS routing, not what is *used*: Comage's
`compare-historical-deals` and Finage's `identify-business-ready-to-invoice`
and `monthly-invoice-report` keep their existing local/OVH-only
`preferred:` provider lists in `policies/model-routing/
model-routing-policy.yaml` unchanged, so no model receives this data
externally as a result of this change alone. Updated in
`components/rag-ingestion/src/rag_ingestion.py` (the actual enforcement
point — a hardcoded per-chunk `classification` value, not the informational
`min_classification`/`default_by_source_type` fields in
`policies/knowledge/knowledge-policy.yaml` and
`knowledge/sxa-legacy/domain.yaml`, which are updated alongside it for
consistency).

## Decision

Treat the two commercial sources as separate logical domains and authority levels:

- **Current commercial knowledge:** `knowledge.sales`, asynchronously ingested from Salesforce.
- **Historical legacy knowledge:** `knowledge.sxa-legacy`, built from validated SXA SQL dumps.

`knowledge.sxa-legacy` contains two semantic layers:

1. **schema knowledge** — tables, columns, keys/relationships and documented business meaning;
2. **authorized historical records** — normalized business records with lineage to source table/row identifiers where feasible.

Retain a structured PostgreSQL representation of SXA and expose **deterministic, policy-controlled query capabilities** for exact aggregations/lookups. Do not expose unrestricted arbitrary SQL generation/execution to the LLM.

Salesforce live MCP remains the authoritative path for current-state verification and writes per ADR-0205. SXA is not used as a fallback current system of record.

Access to `knowledge.sxa-legacy` is explicitly limited to approved Sales and Direction roles/tasks unless a later ADR broadens it. Because legacy dumps can contain historically accumulated sensitive fields, classify the domain conservatively (C3 by default) until a field-level data review establishes lower classifications where justified.

## Consequences

Comage can reason over current Salesforce history and explicitly consult the legacy corpus when needed without confusing the two sources. Direction can access historical institutional knowledge under dedicated policy.

Exact legacy metrics remain reproducible via controlled SQL-backed tools, while semantic questions about old schema/data can use RAG.

## Security considerations

The imported dump, semantic chunks and structured PostgreSQL representation use dedicated credentials/policies. Public repository fixtures remain synthetic/anonymized per ADR-0025. Source row data that cannot be safely classified/authorized must not be indexed.

## Operational considerations

Each legacy import is a versioned snapshot with import timestamp, checksum/provenance and validation report. Re-indexing a snapshot must be idempotent. The knowledge binding and structured-query binding can evolve independently.

## Acceptance criteria

- Current Salesforce records never become indistinguishable from SXA legacy records in metadata/citations.
- An authorized semantic question can search SXA schema plus historical data through `knowledge.sxa-legacy`.
- Exact aggregations can use deterministic structured-query capabilities without arbitrary SQL execution.
- Users without explicit Sales/Direction legacy authorization cannot retrieve SXA chunks or structured query results.
- Salesforce writes never target the SXA database.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0015](0015-use-postgresql-and-pgvector-as-the-persistent-data-platform.md)
- [ADR-0016](0016-migrate-the-legacy-sxa-schema-to-postgresql.md)
- [ADR-0017](0017-access-sales-data-through-controlled-mcp-tools.md)
- [ADR-0025](0025-keep-sensitive-and-real-commercial-data-outside-the-public-repository.md)
- [ADR-0202](0202-introduce-logical-knowledge-domains.md)
- [ADR-0203](0203-enforce-knowledge-authorization-as-policy-intersection.md)
- [ADR-0205](0205-prefer-indexed-knowledge-for-read-and-live-tools-for-freshness-and-write.md)
