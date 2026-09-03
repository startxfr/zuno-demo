# WP-129: generic fetch-oss-docs adapter + per-family knowledge.tech pipelines

- **State:** Repo work merged (2026-09-03) - not yet deployed or
  live-verified, see "Remaining" below.
- **ADRs:** ADR-0105 (amended a second time, this WP). ADR-0202's
  single-`knowledge.tech`-database constraint is preserved unaffected by
  this split, not itself amended - see "Goal" below.
- **Depends on:** WP-100 (the domain-vs-adapter split this WP extends one
  level deeper).
- **Related:** WP-112 (the `qa-go` gap this WP's `crawlStrategy: generic`
  is the prerequisite for eventually closing; also the source of the live
  observation - a manual `tech-redhat` ingestion run triggered to verify
  WP-112 was still running after 4+ hours - that started this WP).
- **Target:** v0.6 (matches ADR-0105's own Target, the ADR this WP amends).

## Goal

`fetch-redhat` crawled all 112 Red Hat product-doc sources strictly
serially in one weekly KFP pipeline (`tech-redhat`), with no way to scope
a subset. A live run confirmed this takes multiple hours end to end.
Measuring the actual source list live showed why: Red Hat OpenShift
Container Platform alone is 76 of the 112 entries (68%); every other
product family (Satellite, AAP, ACM, ACS, Quay, ODF, RHOSO/RHOSP, GitOps/
Argo CD, Helm, Keycloak, RHEL, IdM, MTC, MTA, MTV, Virtualization,
Connectivity Link, OpenShift AI) has only 1-2 entries and sat queued
behind OpenShift's runtime for no reason.

Split `fetch-redhat` into a generalized `fetch-oss-docs` adapter backing
18 independently-scheduled per-family pipelines, fully staggered so no two
`knowledge.tech` pipelines ever overlap, and fix two real concurrency
races the split exposed (one of them pre-existing since WP-100, not
introduced by this WP) rather than deferring them.

## Repo changes (all four phases implemented and committed, 2026-09-03)

**Phase 1** — `components/rag-ingestion/src/rag_ingestion.py`: renamed
`fetch-redhat` → `fetch-oss-docs` end to end (stage name, functions, env
vars `OSS_DOCS_SOURCES_JSON`/`FETCH_OSS_DOCS_CONCURRENCY` with a
one-release fallback to the old names). Added a per-source `crawlStrategy`
field (`redhat-docs` default, unchanged behavior for all 112 existing
entries; `generic` restricts discovery to the same netloc + the source's
own path prefix, for real upstream OSS sites). `_discover_doc_links`
refactored into a shared `_discover_links` both strategies call with a
different filter closure — the fetch pool, conditional-GET/ETag caching
and `_matches_filters` stay shared, unduplicated. `_build_oss_doc_record`
now prefers an explicit per-source `technology` field over the
`TECHNOLOGY_BY_PRODUCT_SLUG` map. 58/58 tests pass
(`components/rag-ingestion/tests/test_source_adapters.py`, extended with a
`crawlStrategy: generic` fixture).

**Phase 2** — `gitops/charts/rag-ingestion/`: `values.yaml`'s `redhat[]`
array (112 entries) each got a `family` field (values.schema.json: now
required, plus `crawlStrategy`/`technology` added to the item schema).
`techSources:` expanded from 2 entries (`redhat`, `confluence`) to 19 (18
families + `confluence` unchanged) — `redhat` renamed to
`redhat-openshift`, reusing its existing Sunday 02:00 cron slot; the other
17 families get the staggered schedule below. `files/pipeline.py.tpl`:
every `configure(..., domain="tech", ...)` call inside the `techSources`
pipeline-def loop now uses `domain="tech-<family>"`; `CONFIGMAPS`/
`PG_SECRETS` dicts now loop over `techSources` instead of one hardcoded
`"tech"` entry (all still pointing at the same shared `knowledge.tech`
Postgres secret — ADR-0202 unaffected); added a `--list-targets` branch to
the compile entrypoint. `ansible/roles/rag_ingestion/tasks/
compile_pipeline_version.yml`: the hand-maintained 3-item target list
(already drifted once) is now derived from `pipeline.py --list-targets`
run against the chart's own rendered pipeline source, closing the
lockstep gap between `pipeline.py.tpl`'s `PIPELINES` dict, `templates/
pipeline.yaml`'s render loop, and this ansible list.

**Phase 3** (folded into Phase 2's new ConfigMap template) — new
`templates/tech-source-configmaps.yaml` (replaces `templates/
configmap.yaml`), one ConfigMap per `techSources` entry with a
family-filtered `OSS_DOCS_SOURCES_JSON` and, critically, its own suffixed
`S3_RAW_PREFIX`/`S3_NORMALIZED_PREFIX`/`S3_MANIFEST_PREFIX`/
`S3_FAILED_PREFIX` — the same pattern `templates/domain-configmaps.yaml`
already used per domain, applied one level deeper. This closes two real
races: `detect-changes` scanning a shared raw prefix would pick up a
sibling pipeline's newly-fetched docs as its own (wasted reprocessing);
`manifest.json`'s unlocked read-modify-write in `stage_validate` could
silently lose a sibling's `deleted_ids` bookkeeping (a last-writer-wins
clobber). `confluence` got its own suffixed prefixes too, closing a
**pre-existing** exposure between today's two `tech-*` pipelines that
WP-100 never fully closed, not just the 17 new ones. `doc_id` (`sha256
(url)[:32]`) and the pgvector `ON CONFLICT (source, chunk_index)` upsert
key both stay URL-keyed, so the prefix split cannot break ADR-0202's
domain-wide dedup — verified directly against the code before relying on
it.

**Phase 4** — `values.yaml`: added `argo-cd.readthedocs.io` (`family:
argocd`) and `helm.sh/docs` (`family: helm`) as `crawlStrategy: generic`
sources, alongside (not replacing) the existing docs.redhat.com-chapter
entries for one comparison cycle. Both URLs confirmed to return 200 before
being added.

### Staggered weekly schedule (Europe/Paris)

| Pipeline | When |
|---|---|
| `redhat-openshift` | Sunday 02:00 (existing slot, unchanged, ~3-4h) |
| `tech-confluence` | every 6h (existing, unchanged) |
| `argocd`, `helm`, `redhat-mtc` | Monday 03:00 / 03:45 / 04:30 |
| `redhat-virtualization`, `redhat-mtv`, `redhat-mta` | Tuesday 03:00 / 03:45 / 04:30 |
| `redhat-quay`, `redhat-odf`, `redhat-openshift-ai` | Wednesday 03:00 / 03:45 / 04:30 |
| `redhat-rhel`, `redhat-keycloak`, `redhat-connectivity-link` | Thursday 02:30 / 03:45 / 04:30 |
| `redhat-aap`, `redhat-acs`, `redhat-acm` | Friday 03:00 / 03:45 / 04:30 |
| `redhat-satellite`, `redhat-openstack` | Saturday 03:00 / 03:45 |

Every non-`redhat-openshift` slot clears by 05:15, ≥45 min before the next
`tech-confluence` firing at 06:00; no family shares a day with
`redhat-openshift`.

## Verification performed (repo-only, no cluster access)

- `components/rag-ingestion`: full test suite green (58/58).
- `helm lint`/`helm template gitops/charts/rag-ingestion`: 0 errors; 20
  `Pipeline` CRs (19 `tech-*` + unchanged `sxa-legacy`); 19 per-family
  ConfigMaps; all 19+ `S3_RAW_PREFIX`/`S3_MANIFEST_PREFIX` values pairwise
  distinct; no rendered occurrence of the old `REDHAT_SOURCES_JSON`/
  `FETCH_REDHAT_CONCURRENCY` env names; spot-checked `redhat-openshift`
  (76 entries), `argocd` (3: 2 Red Hat chapter + 1 upstream), `helm` (3,
  same shape), `redhat-rhel` (4) all filter correctly by family.
  `python pipeline.py --list-targets` run against the actual rendered
  source confirms it already includes non-tech domains (`sxa-legacy`), so
  the ansible derivation needs no manual append.
- Compiled 5 real targets end-to-end through the repo's own `kfp` SDK
  tooling (`tech-redhat-openshift`, `tech-argocd`, `tech-helm`,
  `tech-confluence`, `sxa-legacy`) — all produced valid `PipelineVersion`
  manifests; manually confirmed `tech-argocd`'s compiled manifest mounts
  its own `config-tech-argocd` ConfigMap on all 7 stages.
- `ansible-lint` on the rewritten task: clean (only pre-existing
  `name[casing]` warnings shared with its untouched sibling file).
  `ansible-playbook --syntax-check` against the playbook that includes
  this role: passed, no cluster connection required.

## Remaining (operator actions, not yet done)

Nothing has been applied to the live cluster. Before this WP can move to
Done:

1. Push (already done incidentally — confirm), rebuild the
   `rag-ingestion` image if the CLI rename requires it (check whether the
   image tag/build actually needs to change or whether `:latest` already
   picks up the source rename on next build).
2. `make d1 install rag-ingestion` (or the ansible-role equivalent) to
   apply the 19 `PipelineVersion`s + `Pipeline` CRs + ConfigMaps, and let
   the recurring-run reconciliation create/replace the 19 KFP schedules
   (the existing `cleanup_orphaned_recurring_runs.yml` should retire the
   old single `tech-redhat`/`tech-confluence` shared-prefix state
   automatically — confirm live, not just by design read).
3. **Cold re-fetch expected, not a regression**: every family's first run
   under its new suffixed prefix finds an empty raw prefix and treats
   every doc as new — a one-time full-cost run per family. Don't mistake
   week-one runtimes for a defect.
4. Trigger at least one family pipeline (recommend `argocd` or `helm` —
   smallest, fastest, and exercises the new `crawlStrategy: generic` path
   for real) and confirm a real document-count delta, not just a green
   exit code — the exact trap `agents/tekos/rag/tech.md`'s prior false-pass
   already taught this repo.
5. Once `argocd`/`helm` have real runs from both the Red Hat chapter
   entries and the new upstream sources, compare corpus quality via
   `evaluations/tekos/stress_test.py`'s `qa-argocd`/`qa-helm` probes —
   check the citations' actual `source`/`url`, not just
   `len(citations) > 0` — then decide whether to drop the Red Hat chapter
   stopgap entries.
6. Deliberately exercise the race fix live: trigger two sibling family
   pipelines concurrently (or one scheduled + one on-demand) and confirm
   both `manifest-tech-<family>.json` files converge correctly with no
   lost `deleted_ids`, and each `detect-changes` log shows only its own
   family's doc counts.
