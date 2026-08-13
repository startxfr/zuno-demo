# ADR-0015: Use PostgreSQL and pgvector as the persistent data platform

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

## Decision

Use PostgreSQL for shared persistent state and pgvector/hybrid search, with logical separation by agent/corpus.

## Evolution (2026-08-13)

ADR-0338 refines "logical separation by agent/corpus" into separation by **logical knowledge domain**. `knowledge.tech`, `knowledge.sales`, `knowledge.adv` and `knowledge.sxa-legacy` may share the same PostgreSQL operator/cluster and reusable RAG services, while keeping independently bindable databases/schemas, credentials, policies and lifecycle. Agent definitions must not depend on those physical storage choices.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution and Related ADRs.
