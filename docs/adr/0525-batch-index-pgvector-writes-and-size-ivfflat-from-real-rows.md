# ADR-0525: Batch index-pgvector writes and size ivfflat from real row counts

- **Status:** Implemented (live-verified 2026-08-30) - a real one-off `knowledge.tech`
  domain run (`index-pgvector`, run `5e751c12`) confirmed the batched `executemany()`
  write path live: `943/943 documents processed, upserted 65926 chunk rows, deleted 0
  orphaned rows`, no errors. The live `ix_document_embeddings_embedding_cosine` index
  stayed at `lists='68'` before and after (68945 -> 68962 rows, +17 net new after the
  upsert), exactly matching `clamp(rows/1000, 10, 1000)` - confirms the sizing formula
  is correct in production. The drop/rebuild path correctly did not trigger (net-new
  delta far below the 20%-of-existing-rows threshold), so this run did not exercise
  that branch directly, but `007_ivfflat_lists.sql`'s migration already independently
  produced the same correct `lists` value on this same index (schema-apply Job,
  2026-08-28) using the identical formula. The baseline to beat is ~113k chunk rows in
  ~66 min (~31 rows/s) measured on `knowledge.sxa-legacy` (not re-measured here - this
  run's domain and corpus size differ, so it is not a like-for-like throughput
  comparison, only a correctness verification)
- **Target:** v0.4
- **Date:** 2026-08-27
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0519 fixed the fetch stages and ADR-0520 fixed `detect-changes`. That left
`index-pgvector` as the last serial stage in the pipeline, and it is now the
slowest by a wide margin.

Its S3 side was already parallel - ADR-0219 moved the per-document GET out of
the database loop and into a prefetch pool. What remained was **one
`cur.execute()` per chunk row**. The ingestion pod reaches PostgreSQL through
`zuno-postgresql-pgbouncer.zuno-data.svc:5432` with `sslmode=require`, from a
mesh-injected pod, so every one of those round-trips traverses app → istio
sidecar → pgbouncer → PostgreSQL with TLS on top.

Measured on `knowledge.sxa-legacy`: **~113k chunk rows in ~66 minutes, ~31
rows/s, ~35 ms per row**, projecting to roughly 3 hours for the full 310,537
documents. A local insert against a table with nine indexes costs single-digit
milliseconds, so 35 ms is transport latency, not server work. **The stage is
latency-bound, not index-bound** - which decides the fix.

A second, independent problem surfaced while measuring. The vector index is
built `WITH (lists = 10)`, and `006_embedding_1024.sql` said in a comment that
this was "sized for the small demo corpus". That was true when a domain held
~10k rows. `knowledge.tech` now holds 68,944 and `knowledge.sxa-legacy` is
heading for ~310k, where 10 lists means ~31k vectors per list. Worse, nothing
in the platform set `ivfflat.probes`, so every query ran at the default of 1.

## Decision

1. **Batch the writes.** The driver is psycopg 3, whose `executemany()` uses
   libpq pipeline mode, so a batch costs one flight instead of N round-trips.
   `stage_index_pgvector` accumulates rows and flushes via `executemany()` in
   1000-row batches.

2. **The per-window commit boundary does not move.** Batching happens *inside*
   a window. The existing reasoning still holds and was hard-won: per-run
   commits lost every row to a Patroni failover, per-document commits cost a
   round-trip each. The 2026-08-26 outage killed a run mid-index and the
   `ON CONFLICT ... DO UPDATE` upsert is what made the 112,864 already-written
   rows safe to re-run over, so that upsert is unchanged.

3. **Drop the ivfflat index for a bulk load and rebuild it after**, sized from
   the row count that is then actually present. This removes per-row index
   maintenance from the hot path *and* is the only moment in the system where
   the true count is known - the schema Job necessarily runs against an empty
   table. Sizing follows pgvector guidance for sub-1M corpora,
   `lists = clamp(rows / 1000, 10, 1000)`.

4. **Only for large loads.** Rebuilding a 310k-row index to add five documents
   would cost far more than it saves, so the drop/rebuild is gated on the
   changeset being at least 20% of existing rows, or the table being empty.
   Incremental runs leave the index in place and simply upsert.

5. **The rebuild happens in a `finally`.** If a load fails with the index
   dropped - exactly what the 2026-08-26 outage would have caused - that
   domain's retrieval would silently degrade to sequential scans until someone
   noticed. A failure to recreate is logged at ERROR naming the consequence.

6. **Set `ivfflat.probes` to match.** Raising `lists` without this actively
   harms recall: 310 lists at 1 probe scans ~0.3% of vectors where 10 lists at
   1 probe scanned ~10%. `_init_connection()` in rag-service reads `lists` back
   off the live index and sets `probes` to its square root, per domain, with no
   knob to forget. It is best-effort: a domain whose index is momentarily
   absent falls back to the default rather than failing the connection.

7. **Migrate existing databases.** `CREATE INDEX IF NOT EXISTS` sees an index
   of the right name and does nothing whatever its reloptions, so live
   databases would keep `lists = 10` forever. `007_ivfflat_lists.sql` drops and
   rebuilds when the current value is wrong, and runs *after* 006 because 006
   may itself rebuild the index during the 384→1024 cutover.

## Consequences

- No new `CONFIG_KEYS`. Batch size and the rebuild threshold are derived from
  existing configuration deliberately: a new key would force a ConfigMap
  change, a `CONFIG_KEYS` change and therefore a **new PipelineVersion name**,
  because a PipelineVersion spec is immutable. Stage code lives in the image,
  so this change needs only `make d2 build rag-ingestion`.
- Retrieval for a domain is degraded *during* its own bulk load, while the
  index is dropped. Acceptable for `knowledge.sxa-legacy`, which is an
  on-demand immutable legacy corpus; scheduled domains take the same window.
- HNSW was considered and rejected **for now**. It would remove `lists` tuning
  entirely and improve recall, but HNSW inserts are markedly more expensive
  than ivfflat - directly counterproductive when the goal is faster ingestion.
  It deserves its own ADR argued on query performance, not bolted onto this.

## Acceptance criteria

- `index-pgvector` issues no per-row `INSERT`; rows go out via `executemany`.
- A bulk load leaves `ix_document_embeddings_embedding_cosine` present, with
  `lists` matching `rows/1000` for that domain.
- The index is recreated even when the load raises.
- A rag-service connection reports a non-default `ivfflat.probes`.
- Live: beat the recorded baseline of ~113k rows in ~66 min, and confirm
  retrieval quality per domain has not regressed - the row count cannot prove
  that, and raising `lists` is precisely the change that could harm it.
