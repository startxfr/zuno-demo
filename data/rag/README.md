# RAG Data Configuration

Source catalogs, ingestion configuration and non-sensitive knowledge
metadata are maintained here.

- `schema/003_rag_metadata.sql` - ADR-0046: extends
  `data/sxa/schema/002_pgvector.sql`'s `document_embeddings` table (owned
  by another track) with a nullable `embedding` column, a `UNIQUE`
  constraint on `source`, a bilingual generated `content_tsv` full-text
  column, and expression indexes on `metadata`'s `product`/`version`/
  `classification` keys. See that file's own header comment for the exact
  `metadata` jsonb field convention (`product`, `version`, `language`,
  `source_type`, `classification`, `acl_groups`, `last_modified`,
  `stale_after`, `provenance`).
- `fixtures/seed.sql` - a fictional/synthetic demo corpus (same
  non-nominative-data spirit as `data/sxa/fixtures/seed.sql`, ADR-0025)
  deliberately including conflicting per-version guidance (OpenShift AI
  2.16 vs. 3.5 GPU sizing and ServingRuntime configuration), a bilingual
  (EN/FR) document pair, a classification/ACL-restricted internal
  document, and a stale document - covering ADR-0046's Operational
  consideration ("Add test corpora containing conflicting versions and
  bilingual content").

Applied by `ansible/roles/rag` (after `ansible/roles/sql_schema` has
created the base table) via the same one-shot `psql` Job pattern as
`ansible/roles/sql_schema` itself - see that role's README.
