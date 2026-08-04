# rag

Applies `gitops/apps/rag` (`gitops/charts/rag-service`): pgvector + hybrid
search over the `document_embeddings` table (`components/rag-service`).
CONFIG_SCOPE only — no separate prepare phase. Depends on `postgresql`
(and `sql_schema`, for the table itself) having run first.
