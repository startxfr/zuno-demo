# rag

A Day 1 component (ADR-0056) with a documented no-op `install.yml` - no
operator dependency of its own. Depends on `postgresql` (and
`sql_schema`, for the `document_embeddings` table itself) having run
first.

1. Extends `document_embeddings` with ADR-0046's retrieval metadata support
   (`data/rag/schema/003_rag_metadata.sql` - nullable `embedding`, a
   bilingual generated `content_tsv` column, expression indexes on the
   `metadata` jsonb's `product`/`version`/`classification` keys) and seeds
   the demo fixture corpus (`data/rag/fixtures/seed.sql`), via the same
   one-shot `psql` Job pattern as `ansible/roles/sql_schema` - reusing that
   role's `sql-schema-postgresql-credentials` Secret rather than
   registering a second `ExternalSecret` for the same Vault-backed
   PostgreSQL credential.
2. Applies `gitops/apps/rag` (`gitops/charts/rag-service`): pgvector +
   hybrid search over that table (`components/rag-service`).
