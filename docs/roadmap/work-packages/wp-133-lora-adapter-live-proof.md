# WP-133: Prove the original LoRA-adapter mechanism and close ADR-0301/ADR-0302

- **State:** Repo work merged (2026-09-04) — Parts A-C below merged; the
  GPU pipeline run, adapter promotion PR and live serving verification are
  operator follow-up, not yet done. No status line on ADR-0301/ADR-0302
  changes in this pass - only a live-passing run earns that (Status updates
  below).
- **ADRs:** ADR-0302 then ADR-0301 (their non-superseded decision points -
  see ADR references below; the superseded ones, ADR-0301 pt.1/5 and
  ADR-0302 pt.2/4, stay superseded by ADR-0526 and are untouched here)
- **Depends on:** WP-34 (the `components/mlops`/`gitops/charts/mlops`/
  `gitops/charts/models` mechanism this WP finally exercises), WP-126 (the
  live-proven `TrainJob` step this WP reuses unchanged)
- **Blocks:** none directly, but WP-39/WP-40 (ADR-0303/ADR-0305) were always
  written against this mechanism being live, not ADR-0526's
- **Estimated files touched:** ~10 (Part A ~4, Part B ~5, Part C ~1 new brief)

> Execute this brief as a standalone task from the repository root. Read
> ADR-0301 and ADR-0302 fully - their numbered Decision points are the
> specification this WP finally exercises live, distinct from ADR-0526's
> own (different, already-Implemented) path.

## Goal

WP-34 built a real mechanism - a KFP pipeline that trains a LoRA adapter,
registers it in the Model Registry, and a vLLM native multi-LoRA serving
path that loads it by name/version reference in `gitops/charts/models/
values.yaml`'s `loraAdapters` - but no run has ever exercised it. WP-087's
`wesh` run and WP-126's `TrainJob` proof both went through ADR-0526's
*different* path instead: a merged, standalone bf16 checkpoint served as
its own model, never touching `loraAdapters` (still `[]` today) or
registering anything but a merged artifact. This WP closes that gap: a real
run that registers an actual adapter (not a merge) and serves it through
the multi-LoRA mechanism ADR-0301/ADR-0302 describe, so those two ADRs can
finally move past "coded but never proven" for the decision points ADR-0526
did not supersede.

## Why Tekos + `knowledge.tech`, not Comage

Comage - WP-34's original target - never had usable data:
`knowledge.sales`/`rag-sales` holds 0 rows and `knowledge.project` has no
`document_embeddings` table at all (WP-087's own finding, unchanged since).
Tekos's `knowledge.tech` is the one ADR-0302 point 2-compliant source with
real, growing data as of 2026-09-04: WP-100/WP-129 confirm 570+
`document_embeddings` rows (`redhat-openshift`, `argocd`, `helm` families,
more scheduled), on `answer-technical-question`, a task Tekos actually
routes traffic through today.

## Why merge-export must be skipped, not redirected

`gitops/charts/mlops/values.yaml`'s `mergedModel.s3Uri` is a single shared
value across every agent, pinned to the live-served
`s3://zuno-demo-rag-corpus/models/qwen3.5-9b-wesh` prefix - WP-126 already
proved live that this correctly refuses to run a second time
(`MLOPS_MERGED_OVERWRITE=false`). Giving Tekos its own merge destination
would produce another merged-standalone-model run, i.e. ADR-0526's path
again with a different agent - it would not prove anything ADR-0301/0302's
non-superseded points still need. This WP instead makes `merge-export`
skippable per agent so the DAG goes straight from `train-lora` to
`evaluate` to `push-registry`, reaching `push-registry`'s own
merge-manifest-absent fallback (`components/mlops/src/mlops.py`'s
`stage_push_registry`, already written, never reachable until now) so the
registry entry points at the adapter itself.

## ADR references

- [docs/adr/0301-introduce-lora-and-peft-model-customization.md](../../adr/0301-introduce-lora-and-peft-model-customization.md)
  — points 2 (static selection in `loraAdapters`), 3 (versioned artifact
  referenced by Model Registry name/version, never an ad hoc location), 4
  (classification inheritance/gating). Point 1 (serving mechanism) and 5
  (Comage as starting candidate) stay superseded by ADR-0526 - untouched.
- [docs/adr/0302-build-dataset-to-model-mlops-pipelines.md](../../adr/0302-build-dataset-to-model-mlops-pipelines.md)
  — points 1 (KFP pipeline mechanism), 3 (S3 storage), 5 (evaluation gate
  before promotion), 6 (registry push), 7 (human-reviewed promotion PR,
  never automatic). Points 2 (dataset sourcing) and 4 (training objective)
  stay superseded by ADR-0526 - untouched.
- [docs/adr/0526-fine-tune-and-serve-a-french-urban-register-model-variant.md](../../adr/0526-fine-tune-and-serve-a-french-urban-register-model-variant.md)
  — the *different*, already-Implemented path this WP does not touch or
  re-litigate; `mergedModel`/comage's own `mlops/values.yaml` entry are
  untouched.

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- Read: `gitops/charts/mlops/files/pipeline.py.tpl` (the DAG this WP makes
  conditional), `components/mlops/src/mlops.py`'s `stage_merge_export`/
  `stage_push_registry` (the fallback this WP finally reaches),
  `gitops/charts/models/templates/llminferenceservice-qwen.yaml` (the
  proven multi-LoRA wiring this WP ports), `gitops/charts/models/values.yaml`'s
  `loraAdapters` comment (WP-34's own documented gap: no adapter-download
  mechanism ever existed).

## Repo changes (all merged in this pass)

### Part A — pipeline (`gitops/charts/mlops/`)

1. `values.yaml`: new `agents.tekos` entry - `knowledgeDomains:
   ["knowledge.tech"]` (the literal `metadata->>'domain'` value
   `components/rag-ingestion/src/rag_ingestion.py` writes - "tech" alone
   matches zero rows), `baseModel: s3://zuno-demo-rag-corpus/models/qwen3.5-9b`
   (same checkpoint comage trains against), `skipMerge: true`, same LoRA
   hyperparameters/target-module regex as comage (same base checkpoint
   architecture). `pipeline.version` bumped `v0-2-1` -> `v0-3-0` per this
   file's own "bump on every DAG change" rule.
2. `files/pipeline.py.tpl`: `{{- if $agent.skipMerge }}` branch renders
   `evaluate.after(trained)` directly, omitting `merge_export` from that
   agent's compiled DAG entirely; comage's own branch (the `{{- else }}`)
   is byte-for-byte unchanged.
3. **Fixed a real gap found before launching anything:**
   `ansible/roles/mlops/tasks/compile_pipeline_version.yml`'s
   `_mlops_compile_targets` was hardcoded to `["comage"]` - despite this
   WP's own first-pass claim, per-agent compilation was NOT actually
   generic; a new agent's `PipelineVersion` would never have been compiled
   or uploaded without this fix. Now `["comage", "tekos"]`, per that task's
   own comment ("extend this list when a second candidate agent flips
   on").

### Part B — serving (`gitops/charts/models/`)

4. `templates/llminferenceservice-qwen35.yaml`: ported the classification
   gate (`{{ fail }}` on a non-C1 adapter while `maas.enabled`), the
   `zuno.io/lora-adapter-classifications` annotation, and
   `--enable-lora`/`--lora-modules` args from `llminferenceservice-qwen.yaml`
   (qwen3.6-27b-instruct, WP-34 Part B's original target) - qwen3.5-9b is
   the model Tekos/Comage's routing and the mlops pipeline's `baseModel`
   actually name, unlike the 27B model no LoRA-trained agent targets.
5. **New:** `components/mlops/src/download_adapter.py` - the
   adapter-download mechanism WP-34 documented as an out-of-scope gap and
   nothing since has built. Standalone (does not import `mlops.py`/
   `load_config()`, which assume a KFP stage's full env contract a serving
   pod does not carry); run as an initContainer per `loraAdapters` entry,
   reusing the mlops pipeline's own image (no second image/build target)
   and the base model's existing S3 credential Secret (no new
   ExternalSecret). One `emptyDir` (`/mnt/loras`) shared between every
   download-adapter initContainer and the main container.
6. `values.yaml`/`values.schema.json`: `loraAdapters[]` gains a required
   `sourceS3Uri` field (push-registry's own `registration.json`
   `artifact_uri`, copied verbatim - never a hand-typed location, per
   ADR-0301 point 3); `path` is now schema-constrained to `/mnt/loras/*`
   (the one path the initContainer's volume actually shares with the main
   container). New `loraAdapterDownload.image` value (defaults to the
   mlops image).

### Part C — tests

7. `components/mlops/tests/test_download_adapter.py`: 6 unit tests
   (S3 URI parsing, the empty-prefix refusal, `main()`'s required env vars,
   an end-to-end fake-S3-client download) - fakes only, no live S3/GPU.

## What NOT to touch

- The Decision text of ADR-0301/ADR-0302/ADR-0526 - only ADR-0301/0302's
  `Status:` line moves, and only after a live-passing run (see Status
  updates below).
- `gitops/charts/mlops/values.yaml`'s `comage`/`mergedModel` entries - the
  live-served `wesh` model stays untouched by this WP.
- `gitops/charts/models/values.yaml`'s `loraAdapters` list itself (stays
  `[]` in this pass) and `llminferenceservice-qwen.yaml` (the
  qwen3.6-27b-instruct wiring stays as WP-34 left it - not removed, not
  extended further).
- `policies/model-routing/model-routing-policy.yaml` - no routing change;
  Tekos keeps routing exactly as it does today. This WP only proves the
  adapter can be trained, registered and *loaded*; deciding whether traffic
  should ever prefer it is a separate, later decision.

## Acceptance checks (run from repo root; all must pass)

- `python3 -m pytest components/mlops/ -q` (one pre-existing, unrelated
  failure - `test_resolve_base_model_downloads_s3_uri` - predates this WP)
- `helm lint gitops/charts/mlops gitops/charts/models`
- `helm template gitops/charts/models -s templates/llminferenceservice-qwen35.yaml`:
  no `--enable-lora`/initContainers when `loraAdapters` is empty (default);
  with one C1 entry, `--enable-lora --lora-modules`, the initContainer and
  the shared `/mnt/loras` volume all render; a C2/C3 entry with
  `maas.enabled: true` is rejected by both the schema and the template-time
  `{{ fail }}`; an entry missing `sourceS3Uri` or with a `path` outside
  `/mnt/loras/` is rejected by the schema.
- `python3 platform/security/check_workload_hardening.py` (one
  pre-existing, unrelated failure in `ai-gateway`)
- `python3 platform/supply-chain/check_build_matrix.py` (two pre-existing,
  unrelated missing-matrix-entry findings)
- `ansible-playbook ansible/playbooks/day2_{build,install,check}.yml --syntax-check`
  and `day3_run.yml --syntax-check` (`mlops`/`models` are Day 2 components,
  `mlops`'s run verb is Day 3 - ADR-0060's restructuring; the ORIGINAL WP-34
  brief predates it and still says Day 1, a mismatch this pass corrected
  before running anything)
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up (not executable by the model)

**Correction (2026-09-04, caught before launching anything):** an earlier
pass of this WP wrongly concluded the saturated `zuno-ai-run-gpu-cap`
`ResourceQuota` (`requests.mig-1g.24gb` 3/3, `requests.mig-2g.48gb` 2/2)
blocks this run and needs raising first. It does not: that quota is scoped
to the `zuno-ai-run` namespace only (`gitops/charts/namespaces/templates/
resourcequota-gpu.yaml`, `.Values.openshiftAi.namespace`), which holds the
four *serving* LLMInferenceServices, not the mlops training pipeline.
`zuno-mlops` (where every KFP stage pod and the TrainJob's own trainer pod
actually run) ships with **no ResourceQuota/LimitRange at all, by explicit
design** (`gitops/charts/namespaces/values.yaml`'s own `zuno-mlops` entry:
"No resourceQuota/limitRange here, deliberately mirroring zuno-ai-build:
mlops's train-lora stage needs unconstrained nvidia.com/gpu requests on the
tainted GPU-burst node") - WP-126 already proved this live (a real
`TrainJob` reached `Complete` under this exact saturated `zuno-ai-run`
quota, unaffected by it). The later serving-side step (4 below) is a
rollout-restart of the already-running `qwen35-9b` pod with the same
resource request plus one initContainer that declares no `resources:` at
all - it does not consume additional quota either. No quota change is
needed anywhere in this WP.

1. `make d2 build mlops`, then `make d2 install mlops` (which compiles and
   uploads every `_mlops_compile_targets` `PipelineVersion`, `tekos`
   included per this pass's ansible fix), then launch the run:
   `make d3 run mlops AGENT=tekos`.
2. Confirm live: `prepare-dataset` reads real `knowledge.tech` rows (not
   zero) → `train-lora` (`TrainJob`, WP-126's already-proven path) →
   `evaluate` (ADR-0027/0028 gate) PASS → `push-registry` registers a
   version whose `artifact_uri` is the adapter's own S3 prefix, not a
   merged checkpoint.
3. Review and merge the promotion PR: `gitops/charts/models/values.yaml`'s
   `loraAdapters` gains one entry (`sourceS3Uri` = the registration's own
   `artifact_uri`, `path` under `/mnt/loras/`, `classification` from
   `train_manifest.json`).
4. Sync, confirm `qwen35-9b` rolls out with the adapter's initContainer
   completing and vLLM's `--lora-modules` accepted, and `/v1/models` +
   `make d2 check models` show it loaded and healthy.

## Status updates (then re-run `check_docs.py`)

- After the live run + promotion above are confirmed: ADR-0301's `Status:`
  line records that points 2-4 are now live-verified (this run's id/date),
  alongside its existing "superseded in part" note for points 1/5 - not a
  replacement of that note. ADR-0302 gets the matching update for points
  1/3/5-7. Index rows in `docs/adr/README.md` updated to match (kept
  normalized-equal per `check_docs.py`'s own rule). This WP's own `State`
  line → `Done`; tracker row → `Done`; `MEMORY.md` dated bullet.

## Out of scope / deferred

- Any routing-policy change preferring the adapter for live traffic - this
  WP proves the adapter loads, not that anything should serve from it yet.
- Dynamic per-request adapter selection (WP-39/ADR-0303) and continuous
  benchmarking (WP-40/ADR-0305) - unchanged, still their own later work.
- Extending the download mechanism to `llminferenceservice-qwen.yaml`
  (qwen3.6-27b-instruct) - no agent trains against that base model, so
  there is nothing to prove there yet.
