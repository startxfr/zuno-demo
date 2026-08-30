# WP-100: Split knowledge.tech's ingestion cadence by source (amends WP-22 / ADR-0105)

- **State:** Done (2026-08-30) - `rag-dspa` reached `Ready` this same day,
  clearing the blocker WP-22/WP-07 had carried since 2026-08-17. Ran
  `ansible/playbooks/day2_install.yml -e target_component=rag-ingestion`
  live (local execution - the AAP job-template route hit an unrelated
  `aap-installer` RBAC gap on `ingresses.config.openshift.io`, out of this
  WP's scope): both PipelineVersions compiled, both per-source recurring
  runs created and confirmed `ENABLED` with the correct cron, and the
  cleanup task removed both the old shared orphan and a second orphan
  (`rag-corpus-ingestion-sxa-schedule`, no matching ConfigMap - sxa-legacy
  is on-demand only by design). One manual end-to-end run per source
  `SUCCEEDED` with correct `domain`/`technology` metadata and `source_type`
  populated in `manifest.json`. The tech-confluence recurring schedule then
  auto-fired at its normal 6h cadence while the manual tech-redhat run was
  still finishing - a live concurrency proof of this WP's `_changeset_key`/
  `_owned_by_this_run` scoping: both runs `SUCCEEDED`, `manifest.json`'s
  entry count and `source_type` distribution were unchanged across the
  overlap, and each run's scoped changeset file persisted independently.
- **ADRs:** ADR-0105 (amended 2026-08-30 - see its "Amended" section).
- **Depends on:** WP-22 (merged; this WP does not reopen it - see its own
  amendment bullet).
- **Unblocks:** none.
- **Estimated files touched:** 11.

> Execute this brief as a standalone task from the repository root.

## Goal

WP-22 implemented ADR-0105's per-source cadence decision down to
**domain** granularity, but `knowledge.tech` is the one domain with two
independent source systems (`fetch-redhat` / product-doc web scraping,
`fetch-confluence`) and they still shared one weekly schedule and one KFP
pipeline. Give them independent cadences (redhat weekly, confluence every
6 hours) without splitting `knowledge.tech`'s single database (ADR-0202
requires both sources to stay queryable under one shared vocabulary).

The adapter code itself (`SOURCE_ADAPTERS`, fixture tests, CLI stages) was
already fully separated by WP-22 - this WP closes the remaining
scheduling/pipeline-layer gap.

## Root risk this WP closes

Once `fetch-redhat` and `fetch-confluence` run as two independently
triggered KFP pipelines against one domain, `detect-changes` in one
pipeline could overwrite the other's `<manifestPrefix>/changeset.json`
between its own write and its sibling's `normalize`/`index-pgvector`/
`validate` reads - silently misattributing or dropping new/changed
documents. `components/rag-ingestion/src/rag_ingestion.py` now partitions
the changeset key per run scope (`_changeset_key`) and threads
`source_type` through the manifest so orphan-detection also stays scoped
to only the source(s) a given run actually fetched
(`_run_scope_source_types`, `stage_detect_changes`).

## ADR references

- [docs/adr/0105-automate-source-specific-knowledge-ingestion.md](../../adr/0105-automate-source-specific-knowledge-ingestion.md)
  — "Amended (2026-08-30)" section this WP implements.
- [docs/adr/0202-...](../../adr/) — ADR-0202's cross-source shared-vocabulary
  requirement, which constrains this WP to a scheduling/pipeline split
  only, never a database split.

## Repo changes (already merged)

1. `components/rag-ingestion/src/rag_ingestion.py`: `IngestionConfig.fetch_stages`
   (from `INGESTION_FETCH_STAGES`), `STAGE_SOURCE_TYPES`, `_changeset_key`,
   `_run_scope_source_types`; `stage_detect_changes` carries `source_type`
   into `current`/manifest and scopes `deleted_ids` via `_owned_by_this_run`
   (a manifest entry with unknown `source_type` is never treated as a
   scoped run's to delete); `_load_changeset` reads the scoped key;
   `--fetch-stages` CLI flag added to `main()`.
2. `components/rag-ingestion/tests/test_source_adapters.py`: 5 new tests
   covering scoped changeset keys, scoped/unscoped orphan detection, and
   the missing-`source_type` safety default; one existing assertion
   updated for the new `source_type` field in `current_new_changed`.
3. `gitops/charts/rag-ingestion/values.yaml`: new `techSources.redhat`/
   `techSources.confluence` map (schedule + `fetchStages`, `reconcileAcls`
   flag on confluence only) replacing the old top-level `schedule:` block
   that used to cover both sources.
4. `gitops/charts/rag-ingestion/templates/schedule-configmaps.yaml`:
   renders one ConfigMap per `techSources` entry instead of one shared
   "tech" entry.
5. `gitops/charts/rag-ingestion/files/pipeline.py.tpl`: replaces the
   hardcoded `rag_ingestion_pipeline()` with a generic per-tech-source
   loop (mirrors the existing `domains` loop) producing
   `rag_ingestion_pipeline_tech_redhat`/`_tech_confluence`, both still
   bound to `domain="tech"` (same `CONFIGMAPS["tech"]`/`PG_SECRETS["tech"]`
   entries). `configure()` gained `fetch_stages=` to set
   `INGESTION_FETCH_STAGES` as a task-level env var. Every compiled
   `PipelineVersion` name is now suffixed (no more unsuffixed "tech"
   exemption).
6. `gitops/charts/rag-ingestion/templates/pipeline.yaml`: same
   generalization for the `Pipeline` CRs - two
   `rag-corpus-ingestion-tech-redhat`/`-tech-confluence` CRs replace the
   old bare `rag-corpus-ingestion` one.
7. `ansible/roles/rag_ingestion/tasks/compile_pipeline_version.yml`:
   `_rag_ingestion_compile_targets` updated to `["tech-redhat",
   "tech-confluence", "sxa-legacy"]`.
8. `ansible/roles/rag_ingestion/tasks/cleanup_orphaned_recurring_runs.yml`
   (new): best-effort sweep, included from `install.yml` right after the
   per-ConfigMap recurring-run loop, that deletes any chart-managed
   (`*-schedule` display name) recurring run whose schedule ConfigMap no
   longer exists this run - closes the old shared
   `rag-corpus-ingestion-schedule` recurring run once
   `rag-ingestion-schedule-tech` stops rendering.
9. `knowledge/tech/domain.yaml`: additive `freshness.by_source_class`
   (product-doc weekly, confluence hours-scale); `freshness.objective`
   stays as the domain-wide aggregate/fallback.
10. `platform/docs/check_knowledge_refs.py`: validates that every
    `by_source_class` key names a declared `taxonomy.source_classes` entry
    and carries an `objective`.
11. `docs/adr/0105-...md`: "Amended (2026-08-30)" section added (superseding
    convention, not a rewrite - same pattern ADR-0218 used on this same ADR).

## What NOT touched

- `knowledge.tech`'s database/ConfigMap/Postgres-secret identity (both
  sources still write into the same database - ADR-0202 unaffected).
- WP-22's own `State: Done` (left as-is; this bullet is the cross-reference).
- Salesforce/Aramis scope (ADR-0218's territory, untouched).

## Acceptance checks (run from repo root; all passed during repo-work)

- `python3 -m pytest components/rag-ingestion/ -q` (or the manual runner:
  `components/rag-ingestion/tooling/.venv/bin/python
  components/rag-ingestion/tests/test_source_adapters.py`) - all tests
  pass, including the 5 new ones.
- `helm lint gitops/charts/rag-ingestion` - passes.
- `helm template gitops/charts/rag-ingestion` - confirmed: exactly two
  `rag-ingestion-schedule-tech-*` ConfigMaps (`tech-redhat`,
  `tech-confluence`), never a bare `rag-ingestion-schedule-tech`; two
  `Pipeline` CRs `rag-corpus-ingestion-tech-redhat`/`-tech-confluence`,
  no bare `rag-corpus-ingestion` Pipeline CR.
- Compile smoke test: extracted the rendered `pipeline.py` and ran
  `.venv/bin/python pipeline.py tech-redhat` /
  `pipeline.py tech-confluence` / `pipeline.py sxa-legacy` through the
  pinned `kfp==2.17.0` - all three compile cleanly (`sales` correctly
  `KeyError`s, since it ships `enabled: false`, unchanged pre-existing
  behavior).
- `python3 platform/docs/check_knowledge_refs.py` → `RESULT: PASS`.
- `python3 platform/docs/check_docs.py` → `RESULT: PASS` (confirmed
  2026-08-30, as part of this WP's closure pass).

## Operator / human follow-up (completed 2026-08-30, live on cluster)

1. Deployed via `ansible/playbooks/day2_install.yml -e
   target_component=rag-ingestion` (local execution - AAP job-template
   routing hit an unrelated `aap-installer` RBAC gap on
   `ingresses.config.openshift.io`, out of this WP's scope). Confirmed both
   `rag-corpus-ingestion-tech-redhat` and `rag-corpus-ingestion-tech-confluence`
   Pipelines now have a compiled PipelineVersion (were empty shells before).
2. Confirmed both new recurring runs exist and are `ENABLED` with the
   correct cron via the KFP API. The cleanup task removed the old shared
   `rag-corpus-ingestion-schedule` orphan and a second orphan found live,
   `rag-corpus-ingestion-sxa-schedule` (no matching ConfigMap - expected,
   sxa-legacy is on-demand only by design).
3. Confirmed: one manual end-to-end run per source `SUCCEEDED`, with
   `source_type` populated in `manifest.json` for newly-touched entries.
   The tech-confluence recurring schedule then auto-fired at its normal 6h
   cadence while the manual tech-redhat run was still finishing - both
   completed successfully, and `manifest.json`'s entry count/`source_type`
   distribution were unchanged across the overlap, confirming the scoped-
   orphan-deletion path is safe under real concurrent runs, not just in
   design.

## Out of scope / deferred

- The residual read-modify-write race on `manifest.json` in
  `stage_validate` (each run only ever touches its own changeset's ids, so
  the worst case is a lost progress update from a sibling run, not content
  corruption) - accepted as a documented residual risk, no S3
  conditional-write/ETag concurrency added here.
- Physical deletion of stale raw S3 keys (no fetch adapter deletes a raw
  key today; unchanged by this WP).
