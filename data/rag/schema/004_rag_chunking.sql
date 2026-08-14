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
-- comment). The model actually wired up everywhere in this repo
-- (rag-service's EMBEDDING_MODEL_NAME default, gitops/charts/models'
-- embeddingModel) is BAAI/bge-small-en-v1.5, 384-dimensional. Safe to
-- change: the column is nullable (ALTER in 003) and no real ingestion has
-- ever written to it - only the NULL-embedding demo fixture corpus
-- exists. The explicit `USING embedding::vector(384)` cast (rather than
-- a bare TYPE change) is deliberate: it fails loudly instead of silently
-- corrupting data if this ever runs against an environment that somehow
-- does hold real 1536-dim rows.
DROP INDEX IF EXISTS ix_document_embeddings_embedding_cosine;

ALTER TABLE document_embeddings
    ALTER COLUMN embedding TYPE vector(384) USING embedding::vector(384);

CREATE INDEX IF NOT EXISTS ix_document_embeddings_embedding_cosine
    ON document_embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);

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
