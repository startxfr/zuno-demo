-- Zuno Demo - pgvector-backed document embeddings store
--
-- Implements ADR-0015 ("Use PostgreSQL and pgvector as the persistent data
-- platform"). This table is the shared retrieval corpus queried by the RAG
-- service (Track D) for Tekos and, once enabled, the other agents. It is
-- intentionally generic (source/title/content/embedding/metadata) rather
-- than SXA-specific - it indexes whatever knowledge sources are ingested
-- (Confluence pages, product docs, etc.), not sales transactional data.
--
-- Requires the `vector` extension to be present in the PostgreSQL image
-- (see gitops/charts/postgresql/image/README.md - the default Crunchy
-- Postgres Operator (PGO) operand image does not bundle pgvector either;
-- a custom image is required, and CREATE EXTENSION here will fail loudly
-- if that prerequisite was skipped, which is the intended, non-hand-wavy
-- behavior).
CREATE EXTENSION IF NOT EXISTS vector;

-- 1536 dimensions matches common embedding model output size (e.g.
-- OpenAI text-embedding-3-small/-large family and many local sentence
-- embedding models served via OpenShift AI, ADR-0019/ADR-0020). If Track D
-- selects a model with a different output dimension, this column width is
-- the one thing that needs to change here.
CREATE TABLE IF NOT EXISTS document_embeddings (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source      text        NOT NULL,
    title       text        NOT NULL,
    content     text        NOT NULL,
    embedding   vector(1536) NOT NULL,
    metadata    jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_document_embeddings_source ON document_embeddings (source);
CREATE INDEX IF NOT EXISTS ix_document_embeddings_metadata_gin ON document_embeddings USING gin (metadata);

-- IVFFlat, cosine distance. `lists` is a rough starting point sized for a
-- small demo corpus (rule of thumb ~ rows/1000, floored at a small value);
-- re-tune (and re-ANALYZE) once real ingestion volume is known - see
-- ADR-0105 (v1, automated monthly knowledge ingestion) for the pipeline that
-- will eventually own this table's write path.
CREATE INDEX IF NOT EXISTS ix_document_embeddings_embedding_cosine
    ON document_embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);

COMMENT ON TABLE document_embeddings IS 'Shared pgvector retrieval corpus for the RAG service (ADR-0015); not part of the migrated SXA sales-operations domain.';
