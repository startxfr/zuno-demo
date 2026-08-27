-- Zuno Demo - real chunked ingestion support (ADR-0330 follow-up)
--
-- 003_rag_metadata.sql's own header comment already anticipated this:
-- "A real chunked-ingestion pipeline would need a compound key (source,
-- chunk_index) instead; revisit then." This migration is that revisit,
-- landing alongside the first real (non-fixture) writer of this table:
-- components/rag-ingestion's index-pgvector stage.

-- 002_pgvector.sql sized `embedding vector(1536)` for an OpenAI-class
-- model ("If Track D selects a model with a different output dimension,
-- this column width is the one thing that needs to change here" - its own
-- comment). The model wired up when this file was written was
-- BAAI/bge-small-en-v1.5, 384-dimensional. The explicit
-- `USING embedding::vector(384)` cast (rather than a bare TYPE change) is
-- deliberate: it fails loudly instead of silently corrupting data if this
-- ever runs against an environment that somehow does hold real 1536-dim
-- rows.
--
-- GUARDED 2026-08-27. ADR-0518 moved the fleet to Qwen3-Embedding-0.6B and
-- 006_embedding_1024.sql now widens this same column to vector(1024), but
-- 004 was left narrowing it unconditionally - so on any already-migrated
-- database the cast above aborted with "expected 384 dimensions, not
-- 1024", and the whole schema-apply Job died here under ON_ERROR_STOP=1.
-- The Job could therefore only ever succeed ONCE, on a pre-ADR-0518
-- database: every re-run, every newly enabled domain on an existing
-- cluster, and ADR-0518's own documented `git revert` + re-sync rollback
-- all failed.
--
-- Worse than a failed Job: psql runs each statement in its own
-- transaction, so the DROP INDEX below COMMITTED before the ALTER aborted.
-- Every failed run left the domain's ivfflat index dropped and never
-- rebuilt (006 and 007 were never reached), silently degrading vector
-- search to a sequential scan. Observed live on 2026-08-27 against
-- rag-tech (68,931 rows) and rag-sxa-legacy (319,713 rows).
--
-- The guard is the same shape 006 already uses, keyed on the 1536 that
-- 002 creates: it fires only on a genuinely fresh database and is a no-op
-- at 384 (mid-chain) and at 1024 (post-ADR-0518). The fresh-install
-- trajectory 1536 -> 384 -> 1024 is preserved exactly.
DO $$
BEGIN
    IF (SELECT atttypmod FROM pg_attribute
        WHERE attrelid = 'document_embeddings'::regclass
          AND attname = 'embedding') = 1536 THEN
        DROP INDEX IF EXISTS ix_document_embeddings_embedding_cosine;

        ALTER TABLE document_embeddings
            ALTER COLUMN embedding TYPE vector(384) USING embedding::vector(384);

        CREATE INDEX IF NOT EXISTS ix_document_embeddings_embedding_cosine
            ON document_embeddings USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 10);
    END IF;
END
$$;

-- One row per chunk, not per source document. Existing rows (the demo
-- fixture corpus, one row per document) default to chunk_index 0, which
-- is also correct: they behave as a single-chunk document.
ALTER TABLE document_embeddings
    ADD COLUMN IF NOT EXISTS chunk_index integer NOT NULL DEFAULT 0;

-- Replaces the source-only uniqueness 003_rag_metadata.sql added - a
-- real document now spans multiple rows (one per chunk), so uniqueness
-- has to be per chunk, not per document.
ALTER TABLE document_embeddings DROP CONSTRAINT IF EXISTS uq_document_embeddings_source;

-- PostgreSQL has no ADD CONSTRAINT IF NOT EXISTS - guard explicitly so
-- this migration stays idempotent across ArgoCD's every-sync hook re-run
-- like every other statement in this file (incident 2026-08-14: repeated
-- syncs failed the schema-apply hook Job with "already exists" once the
-- first sync had created this constraint).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_document_embeddings_source_chunk'
    ) THEN
        ALTER TABLE document_embeddings
            ADD CONSTRAINT uq_document_embeddings_source_chunk UNIQUE (source, chunk_index);
    END IF;
END $$;

-- ix_document_embeddings_source (002_pgvector.sql) already covers lookups
-- by source alone (e.g. "delete every chunk of this document") and stays
-- valid as-is; no change needed.

COMMENT ON COLUMN document_embeddings.chunk_index IS 'Position of this row within its source document''s chunk sequence (ADR-0330); 0 for single-chunk/legacy documents.';
