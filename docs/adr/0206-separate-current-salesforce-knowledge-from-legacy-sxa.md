# ADR-0206: Separate current Salesforce knowledge from legacy SXA

- **Status:** To be implemented
- **Target:** v0.2
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team

## Context

The repository already migrates the historical SXA SQL schema into PostgreSQL and exposes controlled sales-data tools. The target information architecture now establishes Salesforce as the current commercial system while retaining SXA only as historical knowledge for Sales and Direction.

Mixing Salesforce and SXA rows in one undifferentiated `sales` corpus would blur authority, freshness and lineage. Conversely, vectorizing the legacy dump alone would lose the precision of structured SQL for exact counts/aggregations and schema exploration.

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
