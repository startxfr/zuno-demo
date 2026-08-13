# ADR-0016: Migrate the legacy SXA schema to PostgreSQL

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

## Decision

Treat the supplied MySQL 5.0-era SXA schema as a migration source and provide a PostgreSQL-native target/bootstrap path.

## Evolution (2026-08-13)

ADR-0206 makes the migrated SXA database explicitly **legacy historical knowledge**, distinct from current Salesforce data. The PostgreSQL-native representation remains useful both for deterministic, policy-controlled structured queries and as the source of a semantic `knowledge.sxa-legacy` index containing schema/relationship metadata plus authorized historical records.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution and Related ADRs.
