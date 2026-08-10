# Vector Data Model

PostgreSQL with pgvector and PostgreSQL full-text search provides the initial vector/hybrid search platform. Logical separation is maintained per agent/corpus and access context. This runs on the same HA PostgreSQL cluster (PgBouncer-fronted, TimescaleDB preloaded) described in `docs/architecture/data-architecture.md`, not a dedicated instance.
