-- Zuno Demo - RAG retrieval metadata (ADR-0046)
--
-- Extends data/sxa/schema/002_pgvector.sql's document_embeddings table
-- (created by another track, ADR-0015) rather than replacing it - this
-- file only ALTERs it, and must run after that one.
--
-- Normalized per-chunk metadata (Decision: "Attach normalized metadata to
-- every indexed chunk: product, version, language, source/source_type,
-- classification, ACL/tenant scope where applicable, last_modified,
-- stale_after and provenance") lives inside the existing GIN-indexed
-- `metadata jsonb` column rather than as new typed columns - it was
-- already schema-owned by another track as an open-ended bag, and every
-- one of these fields is either optional (ACL) or has a small, stable set
-- of values (product/version/language/classification), which jsonb key
-- lookups handle well at this corpus's scale. Convention (enforced by
-- components/rag-service/app/search.py and app/schemas.py, not by a SQL
-- constraint - see that service's own README):
--
--   metadata = {
--     "product":        "openshift-ai" | "openshift" | ...,
--     "version":        "3.5" | "2.16" | ...,
--     "language":       "en" | "fr",
--     "source_type":    "product-doc" | "runbook" | "confluence" | ...,
--     "classification": "C1" | "C2" | "C3"        -- ADR-0034/0035
--     "acl_groups":     ["consultant", "board"]     -- omitted/[] = no ACL restriction
--     "last_modified":  "2026-05-01",
--     "stale_after":    "2027-01-01",               -- optional
--     "provenance":     "https://docs.redhat.com/..." | "zuno-demo-fixture"
--   }

-- Real ingestion (ADR-0105, v1) will populate `embedding` via a live
-- embedding model call; this repo's fixture corpus (data/rag/fixtures/seed.sql)
-- is inserted with a plain SQL script and no live model to call in this
-- environment, so NOT NULL would make seeding impossible. app/search.py's
-- vector query already defensively filters `WHERE embedding IS NOT NULL`
-- (it predates this migration) - that clause was dead code against the
-- original NOT NULL constraint; this makes it real. A row with a NULL
-- embedding still participates in full-text search below.
ALTER TABLE document_embeddings ALTER COLUMN embedding DROP NOT NULL;

-- One row per source document in this demo corpus (no chunking pipeline
-- yet - ADR-0105 v1 territory) - lets fixture seeding be idempotent via
-- ON CONFLICT (source) DO NOTHING. A real chunked-ingestion pipeline would
-- need a compound key (source, chunk_index) instead; revisit then.
--
-- 004_rag_chunking.sql (ADR-0330) is that revisit: it DROPs this constraint
-- and replaces it with UNIQUE (source, chunk_index) once real chunked
-- ingestion exists. This job runs 002/003/004(/005) as one ON_ERROR_STOP=1
-- psql invocation on every ArgoCD sync (no migration-tracking table - every
-- file here must stay idempotent, same principle as 004's own guard
-- comment). Once a domain has real multi-chunk-per-source data, a source
-- legitimately repeats across rows, so re-running this ADD CONSTRAINT
-- unguarded fails forever and 004 is never reached to fix it (incident
-- 2026-08-20: zuno-rag-schema-apply-tech looping on
-- "uq_document_embeddings_source" duplicate-key errors). Guard it the same
-- way 004 guards its own constraint: only add it on a table that has
-- neither constraint yet (a true pre-004 fresh database) - a no-op
-- everywhere else.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_document_embeddings_source'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_document_embeddings_source_chunk'
    ) THEN
        ALTER TABLE document_embeddings ADD CONSTRAINT uq_document_embeddings_source UNIQUE (source);
    END IF;
END $$;

-- Deterministic metadata filters before ranking (Decision) need an index,
-- not a sequential scan through the GIN index's generic containment
-- lookup - expression indexes on the specific keys retrieval actually
-- filters on on the hot path (see search.py's PRODUCT_VERSION_FILTER).
CREATE INDEX IF NOT EXISTS ix_document_embeddings_meta_product
    ON document_embeddings ((metadata ->> 'product'));
CREATE INDEX IF NOT EXISTS ix_document_embeddings_meta_version
    ON document_embeddings ((metadata ->> 'version'));
CREATE INDEX IF NOT EXISTS ix_document_embeddings_meta_classification
    ON document_embeddings ((metadata ->> 'classification'));

-- Bilingual full-text search: a single generated tsvector column whose
-- text-search configuration is chosen per row from metadata->>'language'
-- (defaulting to English for legacy/untagged rows), replacing
-- search.py's previous hardcoded to_tsvector('english', ...) expression -
-- that expression could never match French content's word stems/stopwords
-- correctly regardless of query language.
ALTER TABLE document_embeddings
    ADD COLUMN IF NOT EXISTS content_tsv tsvector
    GENERATED ALWAYS AS (
        to_tsvector(
            CASE WHEN metadata ->> 'language' = 'fr' THEN 'french'::regconfig ELSE 'english'::regconfig END,
            coalesce(title, '') || ' ' || coalesce(content, '')
        )
    ) STORED;

CREATE INDEX IF NOT EXISTS ix_document_embeddings_content_tsv
    ON document_embeddings USING gin (content_tsv);

COMMENT ON COLUMN document_embeddings.metadata IS 'ADR-0046 normalized retrieval metadata - see this file''s header comment for the field convention.';
