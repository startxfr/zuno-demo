# ADR-0519: Parallelize and short-circuit the RAG ingestion fetch stages (fetch-redhat, fetch-sxa)

- **Status:** Implemented (live-verified 2026-08-25 via WP-57 - the SXA fetch stage went from
  127min+ and incomplete to 35m27s, with CPU utilization rising from 4.3% to 89%+)
- **Target:** v0.4
- **Date:** 2026-08-25
- **Decision owners:** Zuno Demo architecture team

## Context

Executing the full re-ingestion ADR-0518 required (embedding dimension
change forces a from-scratch corpus rebuild) showed the `tech` and `sxa`
domain pipeline runs each taking well over an hour. Reading the live code
(`components/rag-ingestion/src/rag_ingestion.py`) rather than guessing
found three precise, unrelated mechanical causes, none touching content
or retrieval quality:

1. `_fetch_redhat` fetched every discovered documentation page with a
   single, strictly sequential `_http_get()` loop - no concurrency, no
   HTTP caching, despite `Last-Modified` already being captured per page
   and never reused.
2. `_split_sql_statements` (used by `_fetch_sxa` to split a mysqldump
   export into statements) was a pure-Python character-by-character state
   machine - an interpreter-overhead-bound pattern, worse on the large
   multi-row `INSERT` statements typical mysqldump output produces.
3. `_fetch_sxa` issued one synchronous S3 `put_object` per row via
   `CorpusStore.put_json`, sequentially, and did this unconditionally
   even when the source dump was byte-identical to the previous run.

## Decision

Four targeted changes to `components/rag-ingestion/src/rag_ingestion.py`,
all mechanical (fetch/parse/write plumbing), none touching chunking,
embedding, `detect-changes`, `normalize`, or any domain besides `tech`
and `sxa`:

1. **`_fetch_redhat` concurrency**: the per-source page-fetch loop runs
   through a `ThreadPoolExecutor`, pool size configurable via
   `FETCH_REDHAT_CONCURRENCY` (chart: `resources.fetch.redhatConcurrency`,
   default 8).
2. **`_fetch_redhat` conditional GET**: each page's `ETag` is now stored
   alongside the existing `last_modified` field; a subsequent fetch sends
   `If-None-Match`/`If-Modified-Since` from the record's previous values,
   and a `304` response skips re-parsing/re-writing that page entirely.
3. **`_split_sql_statements` rewrite**: delegates to `sqlparse.split()`
   (new dependency, pure Python, no C extension) instead of the
   char-by-char loop. `sqlparse.split()` keeps the trailing `;` on each
   statement (verified empirically against this repo's exact edge cases -
   semicolons inside quoted values, comment-only lines), which
   `_INSERT_RE`'s `(?P<values>.+)$` group (`re.DOTALL`) would otherwise
   absorb into the last value - stripped explicitly, a correctness
   requirement, not cosmetic.
4. **`_fetch_sxa` parallel writes + checksum short-circuit**: the
   per-row `put_json` calls run through a `ThreadPoolExecutor`
   (`FETCH_SXA_WRITE_CONCURRENCY` / `resources.fetch.sxaWriteConcurrency`,
   default 8); and before parsing, the dump's sha256 (already computed,
   now computed earlier) is compared against the last known value
   (`{manifest_prefix}/sxa-dump-checksum.json`) - an identical dump skips
   parsing and writing entirely.

Point 4's short-circuit is safe (proven, not assumed) because nothing in
this pipeline ever purges `raw-<domain>/` between runs: `detect-changes`
builds its "current" set purely from listing that prefix
(`stage_detect_changes`), so a skipped write simply leaves the previous
run's already-correct records in place and discoverable - no orphan gets
falsely marked deleted.

## Alternatives considered

- **Batch multiple rows into fewer, larger S3 objects** (fewer PUTs
  overall) instead of parallelizing per-row PUTs: rejected for this WP -
  `raw/<doc_id>.json` (one file per document) is a contract shared by
  every domain's `detect-changes`/`normalize` stage, and restructuring it
  would touch `tech`, `sales`, `confluence`, `adv` and `sxa-legacy` too,
  well beyond this WP's scope, for a marginal additional gain over
  parallelizing the existing per-row writes.
- **A hand-rolled index-based rewrite of `_split_sql_statements`** (no
  new dependency) instead of adopting `sqlparse`: rejected in favor of
  the external library - `sqlparse` is a mature, purpose-built, actively
  maintained SQL tokenizer; less code for this repository to maintain
  correctly against edge cases a hand-rolled parser would only discover
  under load.
- **Dropping the checksum short-circuit** after an initial (mistaken)
  concern that skipping a write could make `detect-changes` treat
  unwritten rows as deleted: re-verified against the actual code (no
  `raw/` purge exists anywhere in the pipeline) and confirmed safe, so
  kept in scope.

## Verification

`components/rag-ingestion/tests/test_source_adapters.py` (CI-safe,
no live source/S3/database): extended with
`test_fetch_sxa_short_circuits_when_dump_checksum_is_unchanged`
(asserts a second identical-dump call returns 0 and never invokes
`_parse_insert_rows`), `test_fetch_redhat_sends_conditional_headers_and_skips_a_304`,
and `test_fetch_redhat_fetches_discovered_links_concurrently` (exercises
the `ThreadPoolExecutor` branch specifically, since the pre-existing
fixture HTML had no discoverable links). Full suite green (45/45) after
these changes, including the pre-existing `_split_sql_statements`/
`_fetch_sxa` idempotency tests (adjusted only to exclude the new
checksum-marker key from generic `store.json` iteration, not to weaken
any assertion).

Live re-ingestion timing comparison (before/after, `tech` and `sxa`
domains) is a separate, explicit operator action - not run automatically
by this ADR/WP.
