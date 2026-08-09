# rag

A Day 1 component (ADR-0056) with a documented no-op `install.yml` - no
operator dependency of its own. Depends on `postgresql` (and
`sql_schema`, for the `document_embeddings` table itself) having run
first.

1. Builds the `zuno-rag-schema` ConfigMap (`data/rag/schema/
   003_rag_metadata.sql` - nullable `embedding`, a bilingual generated
   `content_tsv` column, expression indexes on the `metadata` jsonb's
   `product`/`version`/`classification` keys - plus the demo fixture corpus,
   `data/rag/fixtures/seed.sql`).
2. Applies `gitops/apps/rag` (`gitops/charts/rag-service`): pgvector +
   hybrid search over that table (`components/rag-service`). The chart
   itself applies that ConfigMap's contents against PostgreSQL via an
   ArgoCD `PreSync` hook Job (ADR-0313) before the rest of its resources
   sync - not an ansible-managed Job.
