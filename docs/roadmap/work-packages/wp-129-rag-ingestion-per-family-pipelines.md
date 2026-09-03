# WP-129: generic fetch-oss-docs adapter + per-family knowledge.tech pipelines

- **State:** Operator pending (2026-09-03) - repo work merged AND deployed
  live: all 19 `PipelineVersion`s compiled, all 19 KFP recurring runs
  `ENABLED` with the staggered schedule, the `argocd`/`helm` families each
  triggered and confirmed with a real document-count delta (460/110
  `document_embeddings` rows, DB-verified). Two items remain, see
  "Live rollout (2026-09-03)" below: the other 17 families have not yet had
  their first run (scheduled, not yet due), and the concurrent-run race
  fix has not been deliberately exercised live.
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

## Live rollout (2026-09-03)

ArgoCD's `selfHeal`/`prune` picked up the merged commits automatically
(not a manual `make d1/d2 install`, which surfaced this the hard way mid-
WP-112-verification): the old single `templates/configmap.yaml` was
pruned while a manual `tech-redhat` ingestion run was still in flight,
breaking it with `CreateContainerConfigError` at `detect-changes` (the
`fetch-redhat` stage had already completed all 112 sources over ~3.5h).
That run was terminated (`kfp.Client().runs.terminate_run()`); no data
was lost, just wasted compute.

Getting the new 19-pipeline structure fully live took three real,
unrelated fixes, each confirmed against the actual error before applying:

1. **RBAC gap** (pre-existing, not introduced by this WP - just never
   exercised until 19 brand-new `PipelineVersion`s needed creating at
   once): `zuno-aap-installer`'s `ClusterRole` was missing
   `pipelines.kubeflow.org` (it had the adjacent
   `datasciencepipelinesapplications.opendatahub.io` DSPA-operand group,
   but not the DSP operator's own KFP-native `Pipeline`/`PipelineVersion`
   CRDs). Fixed in `gitops/charts/aap-config/templates/
   clusterrole-installer.yaml`.
2. **Immutable PipelineVersion**: every `techSources` pipeline-def's
   `configure(..., domain=...)` calls changed from the shared literal
   `"tech"` to `"tech-<srcName>"` (needed so each family resolves its own
   ConfigMap) - a real compiled-spec change even for the two *pre-existing*
   targets (`tech-confluence`, and `tech-redhat` now `tech-redhat-openshift`),
   not just the 17 new ones. `pipeline.version` bumped `v0-8-0` -> `v0-9-0`.
3. **Stale image**: the chart already compiled the new `fetch-oss-docs`
   stage name into the pipeline spec, but the `rag-ingestion` container
   image had never been rebuilt from Phase 1's rename - every triggered
   run failed instantly with `argument stage: invalid choice: 'fetch-oss-docs'`.
   Fixed with `make d2 build rag-ingestion` (signed, live).

After all three fixes: all 19 `PipelineVersion`s compiled, all 19 KFP
recurring runs `ENABLED` with the staggered schedule (confirmed via the
v2beta1 API, no stale `tech-redhat-schedule`/`tech-confluence-schedule`
leftovers beyond the unchanged confluence one). `argocd` and `helm` were
each triggered on-demand (their ConfigMaps already contain both the Red
Hat chapter entries and the new upstream `crawlStrategy: generic` sources
- one run exercises both) and `SUCCEEDED`; DB-verified via
`document_embeddings`: 460 `argocd` rows, 110 `helm` rows. A subsequent
`make d3 stresstest agents BULK=0` confirmed `qa-argocd`/`qa-helm`/`qa-go`
all PASS against this real corpus, no regression.

Aside, out of this WP's scope but discovered along the way: the same
stresstest run's `make d3` invocation is now routed through AAP by
default (`zuno_make_aap_mode: auto` in `ansible/confidential.yml`, AAP
newly reachable partway through this session), and AAP's Execution
Environment is missing the `kustomize` binary, failing
`ansible/roles/agents/kustomize`. Worked around by invoking
`ansible/playbooks/day3_stresstest.yml` directly, bypassing the AAP
routing layer for that one run - the EE gap itself is unrelated to
rag-ingestion and not fixed here.

## Remaining (operator actions, not yet done)

1. The other 17 families (everything except `argocd`/`helm`) have not yet
   had their first run - they're scheduled, not yet due. Their first run
   under the new suffixed S3 prefix will be a full cold re-fetch, not
   incremental - expect week-one runtimes higher than steady-state,
   especially `redhat-openshift`'s ~3-4h. Not a regression.
2. Deliberately exercise the race fix live: trigger two sibling family
   pipelines concurrently (or one scheduled + one on-demand) and confirm
   both `manifest-tech-<family>.json` files converge correctly with no
   lost `deleted_ids`, and each `detect-changes` log shows only its own
   family's doc counts.
3. Once there's more signal on the upstream sources' actual coverage
   (right now `argocd`/`helm` chunks aren't broken down by which of the 3
   sources per family they came from), check citations resolve to the new
   upstream URLs specifically, not just `len(citations) > 0` - then decide
   whether to drop the Red Hat chapter stopgap entries.
