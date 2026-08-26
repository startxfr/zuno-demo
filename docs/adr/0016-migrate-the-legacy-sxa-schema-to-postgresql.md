# ADR-0016: Migrate the legacy SXA schema to PostgreSQL

- **Status:** Superseded by ADR-0219
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team
- **Superseded:** 2026-08-26 by [ADR-0219](0219-serve-sxa-only-as-a-historical-rag-corpus.md)

## Decision

Treat the supplied MySQL 5.0-era SXA schema as a migration source and provide a PostgreSQL-native target/bootstrap path.

## Evolution (2026-08-13)

ADR-0206 makes the migrated SXA database explicitly **legacy historical knowledge**, distinct from current Salesforce data. The PostgreSQL-native representation remains useful both for deterministic, policy-controlled structured queries and as the source of a semantic `knowledge.sxa-legacy` index containing schema/relationship metadata plus authorized historical records.

## Superseded (2026-08-21, completed 2026-08-26)

ADR-0216 first moved the *live* structured-query target for real SXA data
to MariaDB (the dump is native mysqldump format; a MariaDB target needs no
schema translation, and this platform already runs MariaDB with the mesh
fix MySQL's wire protocol needs), leaving the PostgreSQL schema/fixtures
this ADR built alive as the local-dev/CI path.

[ADR-0219](0219-serve-sxa-only-as-a-historical-rag-corpus.md) then retired
the structured-query path entirely: SXA is served through RAG only, so
`sales-db` — the sole consumer of this schema in any environment — is
deleted along with `data/sxa/` and the `sql-schema` Day-2 component. This
ADR is therefore now superseded in full, not only in its live-target
clause. There is no PostgreSQL SXA target anywhere.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution and Related ADRs.
