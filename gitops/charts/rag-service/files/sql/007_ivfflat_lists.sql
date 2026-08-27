-- ADR-0525: re-size the ivfflat index for corpora that outgrew the demo.
--
-- 006 builds the index WITH (lists = 10), which is right for the ~10k rows
-- it was sized against but not for what the domains actually hold now:
-- knowledge.tech is at ~69k and knowledge.sxa-legacy at ~310k, where 10
-- lists means ~31k vectors per list.
--
-- CREATE INDEX IF NOT EXISTS cannot fix this - it sees an index of the right
-- name and does nothing, whatever its reloptions - so an existing database
-- keeps lists=10 forever unless something drops it. This file does.
--
-- Runs against a table that may be empty (a fresh install) or already full
-- (an existing cluster), so it sizes from the live count and does nothing
-- when the current lists value is already correct. The ingestion stage
-- re-sizes it again after any bulk load, which is the only moment a truly
-- accurate row count exists; this file exists so a database that never gets
-- re-ingested is not left mis-sized.
DO $$
DECLARE
    v_rows   bigint;
    v_lists  int;
    v_current int;
BEGIN
    IF to_regclass('document_embeddings') IS NULL THEN
        RETURN;
    END IF;

    SELECT count(*) INTO v_rows FROM document_embeddings;
    -- pgvector guidance below 1M rows: lists ~ rows/1000, floored at the 10
    -- that 006 ships and capped so a very large corpus cannot run away.
    v_lists := greatest(10, least(1000, (v_rows / 1000)::int));

    SELECT (regexp_match(pg_get_indexdef(c.oid), 'lists=''?([0-9]+)'))[1]::int
      INTO v_current
      FROM pg_class c
     WHERE c.relname = 'ix_document_embeddings_embedding_cosine';

    IF v_current IS NOT NULL AND v_current = v_lists THEN
        RAISE NOTICE 'ivfflat lists already %, nothing to do', v_lists;
        RETURN;
    END IF;

    RAISE NOTICE 'resizing ivfflat lists % -> % for % rows',
        coalesce(v_current, -1), v_lists, v_rows;
    DROP INDEX IF EXISTS ix_document_embeddings_embedding_cosine;
    EXECUTE format(
        'CREATE INDEX ix_document_embeddings_embedding_cosine '
        'ON document_embeddings USING ivfflat (embedding vector_cosine_ops) '
        'WITH (lists = %s)', v_lists);
END
$$;
