# WP-57: Accelerate the RAG ingestion fetch stages (delivers ADR-0519)

- **State:** Done (2026-08-25). Implemented as briefed: `_fetch_redhat`
  concurrency + conditional GET, `_split_sql_statements` rewritten onto
  `sqlparse`, `_fetch_sxa` parallel S3 writes + dump-checksum
  short-circuit. Full unit suite green (45/45, 3 new tests added). Live
  timing comparison deferred to a separate, explicit operator-triggered
  re-ingestion run (not part of this WP's automated verification).
- **ADRs:** ADR-0519
- **Depends on:** ADR-0518 (the full re-ingestion its rollout required is
  what surfaced these costs in the first place)
- **Blocks:** none
- **Estimated files touched:** ~7

> Execute this brief as a standalone task from the repository root.

## Goal

Cut the wall-clock time of the `tech` and `sxa` RAG ingestion pipeline
runs (observed >1h each during ADR-0518's forced full re-ingestion)
without changing any retrieved content, chunking, or embedding behavior -
purely mechanical fetch/parse/write performance.

## ADR references

ADR-0519 (full file): four changes, all in
`components/rag-ingestion/src/rag_ingestion.py`.

## Preconditions (verify before starting)

- Read `components/rag-ingestion/src/rag_ingestion.py`'s `_fetch_redhat`,
  `_split_sql_statements`, `_fetch_sxa`, `CorpusStore.put_json`, and
  `stage_detect_changes` (to confirm `raw/<domain>/` is never purged
  between runs - the safety argument for the checksum short-circuit).
- Confirm `git status` is clean on `components/rag-ingestion/` and
  `gitops/charts/rag-ingestion/` before editing (parallel sessions commit
  mid-turn in this repository).
- `cd components/rag-ingestion && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest` to have a clean baseline test run.

## Repo changes (step by step)

1. Add `sqlparse>=0.5,<1` to `components/rag-ingestion/requirements.txt`.
2. In `rag_ingestion.py`: add `from concurrent.futures import ThreadPoolExecutor`
   and `import sqlparse`; add `fetch_redhat_concurrency: int` /
   `fetch_sxa_write_concurrency: int` to `IngestionConfig`, wired in
   `load_config()` from `FETCH_REDHAT_CONCURRENCY` /
   `FETCH_SXA_WRITE_CONCURRENCY` env vars (default 8 each).
3. Rewrite `_split_sql_statements` to strip comment lines (unchanged) then
   call `sqlparse.split()`, stripping each statement's trailing `;`
   (required for `_INSERT_RE` correctness - see ADR-0519).
4. Split `_fetch_redhat` into `_build_redhat_record` (pure record
   construction from an already-fetched response) and
   `_fetch_redhat_one` (per-URL: reads any previous record's
   `etag`/`last_modified`, sends a conditional `_http_get`, skips on
   `304`). `_fetch_redhat` keeps its `base_url` fetch unconditional (it
   is already fetched to discover links) and runs every other discovered
   URL through a `ThreadPoolExecutor(max_workers=config.fetch_redhat_concurrency)`.
5. In `_fetch_sxa`: compute the dump checksum immediately after fetching
   bytes (before decoding), compare against
   `{manifest_prefix}/sxa-dump-checksum.json`, return early (0 written)
   on a match. Otherwise parse as before, collect records into a list,
   write them through a `ThreadPoolExecutor(max_workers=config.fetch_sxa_write_concurrency)`
   pool of `put_json` calls, then persist the new checksum.
6. `gitops/charts/rag-ingestion/values.yaml`: add
   `resources.fetch.redhatConcurrency: 8` and
   `resources.fetch.sxaWriteConcurrency: 8`.
7. `gitops/charts/rag-ingestion/templates/configmap.yaml` AND
   `templates/domain-configmaps.yaml` (both - `pipeline.py.tpl`'s
   `CONFIG_KEYS` requires every key in every domain's ConfigMap, a
   previously-hit `CreateContainerConfigError` class of bug): render
   `FETCH_REDHAT_CONCURRENCY`/`FETCH_SXA_WRITE_CONCURRENCY` from the new
   values.
8. `gitops/charts/rag-ingestion/files/pipeline.py.tpl`: add both keys to
   `CONFIG_KEYS`.
9. `components/rag-ingestion/tests/test_source_adapters.py`: add
   `status_code` to `_FakeResponse` (default 200); adjust the two
   existing `_fetch_sxa` tests that iterate `store.json` wholesale to
   exclude/account for the new checksum-marker key; add
   `test_fetch_sxa_short_circuits_when_dump_checksum_is_unchanged`,
   `test_fetch_redhat_sends_conditional_headers_and_skips_a_304`,
   `test_fetch_redhat_fetches_discovered_links_concurrently`.
10. `helm template gitops/charts/rag-ingestion` and confirm the new keys
    render in all three data ConfigMaps (tech + every `enabled: true`
    domain) and in `CONFIG_KEYS`.
11. `cd components/rag-ingestion && .venv/bin/python -m pytest tests/ -q`
    - must be fully green.

## What NOT to touch

Standard list; plus: no change to `detect-changes`, `normalize`, `chunk`,
`embed`, `index-pgvector`, the `raw/<doc_id>.json` one-file-per-document
storage contract, or any domain besides `tech`/`sxa` (`sales`, `adv`,
`confluence`, `sxa-legacy` are untouched - their fetch stages don't share
the code paths changed here beyond the fleet-wide `CONFIG_KEYS`
contract). No live re-ingestion run triggered automatically - that is a
separate, explicit operator action once this WP's code is deployed.
