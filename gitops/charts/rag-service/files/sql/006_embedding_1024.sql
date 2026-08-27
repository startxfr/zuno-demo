-- ADR-0518: the embedding model moves from bge-small-en-v1.5 (384-dim)
-- to Qwen3-Embedding-0.6B (1024-dim). Vectors from the two models live
-- in unrelated spaces, so the existing rows are not migratable - they
-- are TRUNCATEd and the corpus is fully re-ingested by rag-ingestion
-- right after this lands (the operator's big-bang cutover: RAG search
-- returns nothing between this migration and the re-ingestion's embed
-- stage completing).
--
-- TRUNCATE before ALTER on purpose: pgvector can cast between widths
-- but the cast is meaningless across models, and 004's "fail loudly on
-- real rows" USING-cast pattern would abort on the real 846+ chunk
-- corpus this table now holds. Emptying first makes the type change
-- trivially safe and unambiguous.
--
-- Idempotent like the rest of this directory (this file re-runs on
-- every schema-apply Job): the TRUNCATE only fires while the column is
-- still 384-wide, so a re-run after cutover does NOT wipe the
-- re-ingested 1024-dim corpus.
DO $$
BEGIN
    IF (SELECT atttypmod FROM pg_attribute
        WHERE attrelid = 'document_embeddings'::regclass
          AND attname = 'embedding') = 384 THEN
        TRUNCATE TABLE document_embeddings;
        DROP INDEX IF EXISTS ix_document_embeddings_embedding_cosine;
        ALTER TABLE document_embeddings
            ALTER COLUMN embedding TYPE vector(1024);
    END IF;
END
$$;

-- Same ivfflat/cosine shape 004 built for the 384 column. lists=10 is only
-- a starting value: this file runs from a schema Job against a table that is
-- usually still empty, so it cannot know the real row count. 007 re-sizes it
-- afterwards, and the index-pgvector stage re-sizes it again after any bulk
-- load (ADR-0525). Do not read the 10 here as a considered choice for a
-- populated corpus - knowledge.sxa-legacy holds ~310k rows and wants ~310.
CREATE INDEX IF NOT EXISTS ix_document_embeddings_embedding_cosine
    ON document_embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);
