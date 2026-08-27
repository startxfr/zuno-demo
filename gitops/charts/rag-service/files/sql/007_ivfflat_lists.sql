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
--
-- It RESIZES an existing index; it never creates a missing one. See the
-- guard below for why.
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

    -- 2026-08-27: an ABSENT index is not this file's job to create, and
    -- treating it as "needs rebuilding" made things worse rather than
    -- better. 006 creates it on a fresh database while the table is still
    -- empty, and rag-ingestion's index-pgvector stage recreates it after
    -- any bulk load (_rebuild_vector_index, CREATE INDEX IF NOT EXISTS).
    -- Both of those build it at a moment when building it is cheap or
    -- properly resourced; this Job is neither. It runs with
    -- activeDeadlineSeconds: 300, and - measured that same day against the
    -- 319,713-row sxa-legacy corpus - the build needs 87 MB of
    -- maintenance_work_mem against this server's 64 MB default, so it
    -- would abort outright and, under ON_ERROR_STOP=1, fail the whole
    -- schema apply for every domain. Defer instead, loudly.
    IF v_current IS NULL THEN
        RAISE NOTICE 'ivfflat index absent for % rows - deferring creation to rag-ingestion''s index-pgvector stage', v_rows;
        RETURN;
    END IF;

    IF v_current = v_lists THEN
        RAISE NOTICE 'ivfflat lists already %, nothing to do', v_lists;
        RETURN;
    END IF;

    RAISE NOTICE 'resizing ivfflat lists % -> % for % rows', v_current, v_lists, v_rows;
    -- Same measured ceiling as above: the requirement scales with `lists`,
    -- so a corpus that merely grows starts failing here with no other
    -- change. Mirrors what rag_ingestion.py's _rebuild_vector_index sets,
    -- for the same reason. Session-scoped, held only for this build.
    SET LOCAL maintenance_work_mem = '512MB';
    DROP INDEX IF EXISTS ix_document_embeddings_embedding_cosine;
    EXECUTE format(
        'CREATE INDEX ix_document_embeddings_embedding_cosine '
        'ON document_embeddings USING ivfflat (embedding vector_cosine_ops) '
        'WITH (lists = %s)', v_lists);
END
$$;
