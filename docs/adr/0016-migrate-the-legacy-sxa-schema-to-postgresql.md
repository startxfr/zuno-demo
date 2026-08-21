# ADR-0016: Migrate the legacy SXA schema to PostgreSQL

- **Status:** Superseded by ADR-0216 (live-target clause only — see 2026-08-21 note)
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

## Decision

Treat the supplied MySQL 5.0-era SXA schema as a migration source and provide a PostgreSQL-native target/bootstrap path.

## Evolution (2026-08-13)

ADR-0206 makes the migrated SXA database explicitly **legacy historical knowledge**, distinct from current Salesforce data. The PostgreSQL-native representation remains useful both for deterministic, policy-controlled structured queries and as the source of a semantic `knowledge.sxa-legacy` index containing schema/relationship metadata plus authorized historical records.

## Superseded (2026-08-21)

ADR-0216 moves the *live* structured-query target for real SXA data to
MariaDB (the dump is native mysqldump format; a MariaDB target needs no
schema translation, and this platform already runs MariaDB with the mesh
fix MySQL's wire protocol needs). The PostgreSQL schema/fixtures this ADR
built are **not removed** — they remain the local-dev/CI path. See
ADR-0216 for the full decision.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution and Related ADRs.
