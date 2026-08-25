# WP-58: Parallelize the detect-changes read stage (delivers ADR-0520)

- **State:** Done (2026-08-25). Implemented as briefed:
  `stage_detect_changes`'s per-document S3 read loop now runs through a
  `ThreadPoolExecutor` (`DETECT_CHANGES_READ_CONCURRENCY`, default 16),
  and `CorpusStore`'s shared S3 client got an explicit
  `max_pool_connections=32` so that concurrency isn't silently capped by
  botocore's default of 10. Full unit suite green (47/47, 2 new tests -
  `detect-changes` had zero prior coverage). **Live-verified 2026-08-25**:
  built, deployed, and re-run against the `sxa` domain (314,428 raw
  objects) - `detect-changes` dropped from **3h48m17s** (pre-WP-58 run,
  same domain) to **13m25s**, a ~17x speedup consistent with the
  concurrency knob's default of 16. Full run (`fetch-sxa` through
  `index-pgvector`) completed end-to-end (SUCCEEDED) in 16m51s.
- **ADRs:** ADR-0520
- **Depends on:** WP-57/ADR-0519 (this WP's bottleneck was only exposed
  once `fetch-sxa` became fast enough to stop masking it)
- **Blocks:** none
- **Estimated files touched:** ~7

> Execute this brief as a standalone task from the repository root.

## Goal

Cut the wall-clock time of the `detect-changes` stage (observed >3h47m
and still running, on the `sxa` domain's 314,428 raw documents, in a
live post-WP-57 re-ingestion run) without changing the
new/changed/deleted/unchanged classification logic - purely mechanical
read-concurrency, the same class of fix WP-57 already applied to
`fetch-redhat`/`fetch-sxa`.

## ADR references

ADR-0520 (full file): two changes, both in
`components/rag-ingestion/src/rag_ingestion.py`.

## Preconditions (verify before starting)

- Read `components/rag-ingestion/src/rag_ingestion.py`'s
  `stage_detect_changes` and `CorpusStore.__init__` (to confirm the
  sequential-GET loop and the S3 client's connection-pool defaults).
- Confirm `git status` is clean on `components/rag-ingestion/` and
  `gitops/charts/rag-ingestion/` before editing (parallel sessions commit
  mid-turn in this repository).
- `cd components/rag-ingestion && .venv/bin/pip install -r requirements.txt pytest`
  (rebuild the venv if `sqlparse` - added by WP-57 - is missing) to have
  a clean baseline test run.

## Repo changes (step by step)

1. In `rag_ingestion.py`: add `detect_changes_read_concurrency: int` to
   `IngestionConfig`, wired in `load_config()` from
   `DETECT_CHANGES_READ_CONCURRENCY` (default 16).
2. In `CorpusStore.__init__`'s `BotoClientConfig`, add
   `max_pool_connections=32`.
3. In `stage_detect_changes`, replace the sequential
   `for key in raw_keys: record = store.get_json(key)` loop with a
   `ThreadPoolExecutor(max_workers=config.detect_changes_read_concurrency)`
   and `pool.map(store.get_json, raw_keys)`, folding results into
   `current` on the calling thread (order-preserving, no lock needed).
   Nothing downstream of `current` changes.
4. `gitops/charts/rag-ingestion/values.yaml`: add
   `resources.detectChanges.readConcurrency: 16`.
5. `gitops/charts/rag-ingestion/templates/configmap.yaml` AND
   `templates/domain-configmaps.yaml` (both - `pipeline.py.tpl`'s
   `CONFIG_KEYS` requires every key in every domain's ConfigMap):
   render `DETECT_CHANGES_READ_CONCURRENCY` from the new value.
6. `gitops/charts/rag-ingestion/files/pipeline.py.tpl`: add the key to
   `CONFIG_KEYS`.
7. `components/rag-ingestion/tests/test_source_adapters.py`: import
   `stage_detect_changes`; add
   `test_stage_detect_changes_classifies_new_changed_deleted_unchanged`
   and `test_stage_detect_changes_reads_raw_records_concurrently`.
8. `helm template gitops/charts/rag-ingestion` and confirm
   `DETECT_CHANGES_READ_CONCURRENCY` renders in all three data
   ConfigMaps (tech + every `enabled: true` domain) and in
   `CONFIG_KEYS`.
9. `cd components/rag-ingestion && .venv/bin/python -m pytest tests/ -q`
   - must be fully green.

## What NOT to touch

Standard list; plus: no change to the new/changed/deleted/unchanged
classification logic itself, `normalize`, `chunk`, `embed`,
`index-pgvector`, `_fetch_redhat`/`_fetch_sxa` (already WP-57), the
`raw/<doc_id>.json` one-file-per-document storage contract, or the two
other, dedicated S3 clients (sxa-dump, sxa-corpus) - only
`CorpusStore`'s shared client gets the connection-pool change. No live
re-ingestion run triggered automatically - that is a separate, explicit
operator action once this WP's code is deployed.
