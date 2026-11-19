# Vector Data Model

Last reviewed: 2026-11-19

Knowledge vectors live in **Qdrant inside the UnifAI stack**, not in PostgreSQL. [ADR-0568](../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md)
(Implemented 2026-11-05) replaced the earlier design, which held chunks in PostgreSQL with pgvector and full-text search through a
`rag-service` and a `rag-ingestion` pipeline; neither exists in `gitops/charts` any more. The data layout as a whole is in
[data architecture](../architecture/data-architecture.md).

## Logical model

- **One collection per logical knowledge domain**, for example `knowledge.tech` (product documentation and technical Confluence) and
  `knowledge.sxa-legacy` (the historical commercial record). The domains an agent may read are declared in its signed definition and in
  the corp knowledge policy of the agents release, not on this page.
- **Hybrid search**: dense and sparse vectors fused at query time.
- **Access context**: every query carries a fail-closed `acl_groups` filter taken from the caller's Keycloak groups; a person's own uploads
  are private to that person, shared sources are readable by the groups listed on each source
  ([live RAG scenario](../demo/unifai-live-rag.md)).
- **Embeddings** stay on OpenShift AI: `qwen3-embedding-0.6b`, 1024 dimensions, behind the `embeddings-predictor` service in `zuno-ai-run`
  (`gitops/charts/unifai/values.yaml`). docling converts uploaded files to text before chunking.
- **Agent memory**: the memory tool reads the same Qdrant.

## Where pgvector remains

PostgreSQL still bundles the pgvector extension in the operand image, and the OpenShift AI GenAI playground runs its own small
`genai-pgvector` for the documents uploaded in the playground ([AI architecture](../architecture/ai-architecture.md)). Neither is the Zuno
knowledge store.

## Retention and backup

Qdrant snapshots and a Mongo dump are taken by the UnifAI stack (`spec.backup`) into the `unifai/` prefix of the backups bucket; see
[data retention](data-retention.md) and [backup and recovery](../platform/backup-recovery.md).
