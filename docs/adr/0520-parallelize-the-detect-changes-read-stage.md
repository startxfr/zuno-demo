# ADR-0520: Parallelize the detect-changes read stage

- **Status:** Proposed
- **Target:** v0.4
- **Date:** 2026-08-25
- **Decision owners:** Zuno Demo architecture team

## Context

WP-57/ADR-0519 fixed `fetch-sxa`'s wall-clock time (127+ minutes,
incomplete, down to 35m27s live-verified after deployment - a real CPU
utilization jump from 4.3% to 89%+). Once that fix was live and a fresh
`sxa` re-ingestion run restarted, the pipeline's next stage,
`detect-changes`, ran for over three and a half hours without
completing. Live diagnosis (`ps aux` on the running pod, repeated CPU-time
checks) confirmed the process was not stuck or crashed - it was steadily
consuming CPU, just very slowly.

Reading the code (`stage_detect_changes`,
`components/rag-ingestion/src/rag_ingestion.py`) found the exact cause:

```python
raw_keys = [k for k in store.list_keys(f"{config.raw_prefix}/") if k.endswith(".json")]
current: dict = {}
for key in raw_keys:
    record = store.get_json(key)
    ...
```

a single, strictly sequential S3 `get_object` per document under
`raw-<domain>/`. Confirmed live via `aws s3api list-objects-v2 --prefix
"raw-sxa/"`: **314,428** objects for the `sxa` domain alone - an order of
magnitude more than what `fetch-sxa` itself processes per run, which is
why this bottleneck was invisible until WP-57 made `fetch-sxa` fast
enough to stop masking it. Mechanically identical to the class of
problem ADR-0519 already solved: network/S3-latency-bound, not
CPU-bound, safely parallelizable.

## Decision

One change to `components/rag-ingestion/src/rag_ingestion.py`:

1. **`stage_detect_changes` read concurrency**: the per-key `get_json`
   loop that rebuilds the `current` doc-id/sha256/url map runs through a
   `ThreadPoolExecutor`, pool size configurable via
   `DETECT_CHANGES_READ_CONCURRENCY` (chart:
   `resources.detectChanges.readConcurrency`, default 16 - double
   WP-57's pools, since a bare JSON GET with no HTML/SQL parsing is
   lighter per call and this stage's object count is an order of
   magnitude higher). `pool.map` is used specifically because it
   preserves input order, so the `current` dict is populated back on the
   calling thread from an ordered result stream - no lock, no concurrent
   dict mutation, and no change to the new/changed/deleted/unchanged
   classification logic that follows.
2. **`CorpusStore`'s shared S3 client gets an explicit
   `max_pool_connections=32`**. botocore's default is 10, below this
   stage's new default concurrency of 16; without raising it, threads
   beyond the pool limit would queue for a connection instead of running
   in parallel, silently capping the achieved concurrency below what the
   new knob configures. WP-57's own concurrency knobs (8 and 8) never
   hit this limit because neither pool's own size, alone, exceeded 10.

Nothing else about `stage_detect_changes` changes: the manifest read,
the new/changed/deleted/unchanged classification, `corpus_incremental`,
`corpus_delete_orphans`, and the `changeset.json`/`manifest.json` writes
are untouched.

## Alternatives considered

- **Batch multiple raw-object reads into fewer S3 calls** (e.g. a
  manifest-of-manifests, or `ListObjectsV2` metadata instead of full
  `GetObject`): rejected - `raw/<doc_id>.json` is a one-file-per-document
  contract shared by every domain's `detect-changes`/`normalize` stage
  (ADR-0519's own "alternatives considered" already rejected
  restructuring this for the same reason); the per-document sha256/url
  fields this stage needs are only available inside the object body, not
  in S3-side metadata, so a full `GetObject` per document is
  unavoidable without a much larger restructuring.
- **Leaving `max_pool_connections` at its botocore default**: rejected -
  would silently cap the new concurrency knob's effect at ~10 workers
  regardless of configuration, defeating the point of making it
  configurable.

## Verification

`components/rag-ingestion/tests/test_source_adapters.py` (CI-safe, no
live S3/database): `detect-changes` previously had zero test coverage.
Added `test_stage_detect_changes_classifies_new_changed_deleted_unchanged`
(baseline correctness guard: new/changed/deleted/unchanged classification
and manifest contents, unaffected by this WP) and
`test_stage_detect_changes_reads_raw_records_concurrently` (exercises the
`ThreadPoolExecutor` branch with a pool smaller than the number of raw
keys, confirms every per-document result still lands in `current`
correctly regardless of thread scheduling). Full suite green (47/47).

Live re-ingestion timing comparison (`sxa` domain, before/after) is a
separate, explicit operator action - not run automatically by this
ADR/WP, same convention as ADR-0519.

**Live result (2026-08-25):** after building and deploying this change,
the in-flight `sxa` run (started before the deploy, still on the old
image) was cancelled and a fresh run triggered against the same domain
(314,428 raw objects under `raw-sxa/`). `detect-changes` completed in
**13m25s** (20:05:51-20:19:16 UTC), down from **3h48m17s** on the same
domain's prior run (14:59:00-18:47:17 UTC) - a ~17x speedup, consistent
with the new concurrency default of 16. The full pipeline run
(`fetch-sxa` through `index-pgvector`) reached `SUCCEEDED` end-to-end in
16m51s; downstream stages after `detect-changes` finished in seconds
because the changeset was empty (the cancelled prior run had already
written an up-to-date manifest before being terminated mid-`normalize`),
not because of any change made by this ADR.
