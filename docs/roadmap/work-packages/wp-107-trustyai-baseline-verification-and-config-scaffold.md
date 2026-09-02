# WP-107: TrustyAI baseline verification and the trustyai-config scaffold

- **State:** Done — live-verified 2026-09-02 on demo222. `Ready=True`/`TrustyAIReady=True` on
  `zuno-dsc`; `make d2 install trustyai-config` and `make d3 check trustyai-config` both green
  (scaffold Applications Synced/Healthy, shared LMEvalJob report wired); the ADR-0108
  non-regression check found and FIXED a real regression (see Live findings below - the LM-Eval
  gate had been silently broken since ADR-0521's https cutover), closing on a fresh
  `Complete`/`Succeeded` run: `mmlu_abstract_algebra acc=0.72` over 100 samples, 29.2s eval time,
  through mesh TLS origination. Commits `9a7a5120` (scaffold) and `690892da` (double-TLS fix).
- **ADRs:** ADR-0534 (Accepted, Phase 1)
- **Depends on:** ADR-0108/WP-10 (Implemented - the existing LMEvalJob model-benchmarking gate this
  WP verifies rather than re-does)
- **Related:** WP-072/WP-073 (`aap`/`aap-config`), WP-085 (`lightspeed`/`lightspeed-config`) - the
  two-component pattern this WP's `trustyai-config` scaffold mirrors, minus the Day 1 half, since
  there is no operator to install here
- **Unblocks:** WP-108 (Phase 2 infra), WP-109 (Phase 2 Zuno wiring + Phase 3 model comparison)

## Goal

Confirm that TrustyAI's operand health goes beyond the LM-Eval path already exercised by
ADR-0108/WP-10, formally document `spec.components.trustyai` as the shared configuration surface
ADR-0534's later phases will extend, and stand up an empty `trustyai-config` Day 2 component
(chart, Ansible role, ArgoCD Application pair, Makefile wiring) ready for WP-108/WP-109 to populate.
No guardrails functionality, no RAGAS/Garak, no new evaluation logic is introduced by this WP.

## Why this is not an operator install

TrustyAI is **already** a `Managed` component of the `DataScienceCluster`
(`gitops/charts/openshift-ai/values.yaml`, `spec.components.trustyai`), installed as part of the
existing Day 1 `openshift-ai` component (already in `DAY1_RUN_COMPONENTS`, `Makefile:45`). It has
backed ADR-0108/WP-10's `LMEvalJob` benchmarking gate since that WP shipped. There is no new
`Subscription`, `OperatorGroup` or namespace to create, unlike `aap`/`lightspeed`. "Deploy operator
+ fundamentals" for TrustyAI therefore means: verify the existing operand, document its shared
config surface, and prepare the infrastructure (`trustyai-config`) that later WPs will need - not
install anything new.

## Component and file layout

| | Day 1 - `openshift-ai` (existing, untouched functionally) | Day 2 - `trustyai-config` (new, this WP) |
|---|---|---|
| Role | `ansible/roles/openshift_ai/tasks/{install,precheck,uninstall}.yml` (existing) | `ansible/roles/trustyai_config/tasks/{install,precheck,uninstall}.yml` (new) |
| Chart | `gitops/charts/openshift-ai` (existing) | `gitops/charts/trustyai-config` (new) |
| Apps | `zuno-openshift-ai-d0`/`-d1` (existing, carries the `DataScienceCluster` incl. `spec.components.trustyai`) | `zuno-trustyai-config-d0` (renders nothing, like `lightspeed-config-d0`) -> `gitops/charts/noop`; `zuno-trustyai-config-d1` (this WP: health-check only) |
| Contains (this WP) | Explanatory comments only, above the existing `trustyai:` block - no functional change | Chart skeleton, a Job or Ansible task re-exercising the existing LMEvalJob precheck pattern under the new component's namespace/label, nothing guardrails-specific yet |
| Depends on | OLM/RHOAI subscription only (unchanged) | `models` (LMEvalJob lives in `zuno-ai-run`, same namespace `models` provisions) |

Makefile placement, mirroring `lightspeed-config`'s slot exactly:

- `DAY2_RUN_COMPONENTS` (`Makefile:67`): insert `trustyai-config` after `mlops`, before
  `lightspeed-config`/`supply-chain` - it has no dependency on `lightspeed`/`lightspeed-config` and
  should not block or be blocked by them.
- `ansible/playbooks/day2_install.yml` `day2_components`: same entry, same position.
- `DAY3_CHECK_ONLY_COMPONENTS` (`Makefile:102`): append `trustyai-config` - like
  `lightspeed`/`lightspeed-config`, this component supports `check` only at this stage, not
  `test`/`stresstest`/`backup`/`restore`.

## Steps

### Step 1 - live verification of the existing operand (no repo change)

- `oc get datasciencecluster zuno-dsc -o jsonpath='{.status.conditions}'` and confirm the
  `trustyai` component's own condition (not just the aggregate DSC condition) reports healthy -
  ADR-0534's Phase 1 explicitly asks for this "beyond the LM-Eval path already exercised".
  ADR-0108/WP-10 verified the LMEvalJob mechanics; this step verifies the operand's general health
  independent of any specific job.
- Re-run (or confirm the latest run of) the existing LMEvalJob path
  (`gitops/charts/models/templates/lmevaljob.yaml`, checked by
  `ansible/roles/models/tasks/precheck.yml`) and confirm `state: Complete` /
  `reason: Succeeded` still holds - a regression check, not new functionality.
- Record both results here once run (operator step).

### Step 2 - document the shared configuration surface

- `gitops/charts/openshift-ai/values.yaml`: add a comment block directly above the `trustyai:` key
  (around line 193) explaining that `eval.lmeval` backs ADR-0108/WP-10 (Implemented) and that
  `mcpGuardrailsMode` is the flag ADR-0534/WP-108 will flip - so a future reader does not need to
  chase two ADRs to understand one YAML block. No functional change to the rendered values.
- `docs/platform/` (whichever page documents RHOAI components, e.g. the OpenShift AI component
  page): add or extend the TrustyAI entry to reference ADR-0108 (benchmarking, Implemented) and
  ADR-0534 (evaluation/guardrails, Accepted, WP-107/108/109 in progress).

### Step 3 - scaffold `trustyai-config`

- `gitops/charts/trustyai-config/`: minimal Helm chart (`Chart.yaml`, `values.yaml`, `templates/`)
  following the same skeleton `lightspeed-config` used at its own creation - see
  `gitops/charts/lightspeed-config/Chart.yaml` for the boilerplate to copy.
- `gitops/apps/trustyai-config/application-d0.yaml`: renders nothing, points at
  `gitops/charts/noop`, exactly like `gitops/apps/lightspeed-config/application-d0.yaml`.
- `gitops/apps/trustyai-config/application-d1.yaml`: points at the new chart; this WP's only
  content is a health-check Job or CronJob that re-exercises
  `ansible/roles/models/tasks/precheck.yml`'s LMEvalJob-lookup pattern (call the same task file via
  `include_tasks`/`import_tasks` rather than copying its logic - ADR-0534's Operational
  considerations explicitly asks for reuse over reinvention).
- `ansible/roles/trustyai_config/tasks/install.yml` / `precheck.yml` / `uninstall.yml`: new role,
  `install.yml` applies the `-d0`/`-d1` Application pair via the standard
  `ansible/tasks/apply_gitops_app.yml` mechanism; `precheck.yml` performs the health check above;
  `uninstall.yml` mirrors `lightspeed_config`'s uninstall shape.
- Wire into `Makefile`/`ansible/playbooks/day2_install.yml`/`day3_check.yml` per the placement
  above.

## What NOT to touch

- Do not create any new `Subscription`/`OperatorGroup`/namespace for TrustyAI - it already has one,
  owned by `openshift-ai`.
- Do not flip `mcpGuardrailsMode` - that is WP-108's first step, gated on this WP's baseline being
  green.
- Do not add RAGAS/Garak manifests yet - `trustyai-config`'s chart in this WP renders only the
  health-check Job, nothing evaluation-specific.

## Verification checklist (operator step - ask before running)

- `make d1 check openshift-ai` reports the `trustyai` DSC component condition healthy.
- The existing LMEvalJob run still shows `state: Complete` / `reason: Succeeded` (no regression).
- `make d2 install trustyai-config` syncs `zuno-trustyai-config-d0` and `-d1` to Synced/Healthy.
- `make d3 check trustyai-config` passes (health-check Job succeeds).
- `python3 platform/docs/check_docs.py` passes (ADR/WP status and tracker rows stay consistent).
- Commit, push, and record the live results above before marking this WP `Done`.

## Live findings (2026-09-02)

1. **The LMEvalJob path WAS regressed - Step 1's non-regression check caught a real defect.** The
   standing `qwen36-27b-instruct-mmlu` result was a stale `Complete/Failed`
   (`ContainerStatusUnknown`, a node disruption relic from 2026-08-26). Two fresh runs then failed
   deterministically with `[SSL] record layer failure` on the very first request: since ADR-0521
   moved qwen to an `LLMInferenceService` (TLS on 8000), the KServe controller auto-generates a
   `DestinationRule` (mode SIMPLE, service-ca, SNI) and the mesh-injected job pod's sidecar
   originates TLS on top of the client's own https handshake - double-TLS. `ai-gateway` avoids
   this via `traffic.sidecar.istio.io/excludeOutboundPorts: "8000"` on its own pod, but the
   LMEvalJob CRD's `spec.pod` exposes no annotations field (verified via `oc explain`,
   3.5.0-ea.2), so the exclusion path is unavailable. Fix (commit `690892da`): the job's
   `base_url` is now plain `http://` with `trustLocalCA` off, letting the sidecar do the verified
   TLS origination - the mesh-native path. This means the LM-Eval gate had been silently broken
   since the 2026-08-25/26 ADR-0521 cutover; nothing re-ran it until this WP.
2. The `zuno-trustyai-config-d0` Application's first apply failed with `app path does not exist` -
   ArgoCD clones `origin/main`, and the chart existed only locally. Commit and push BEFORE
   `make d2 install trustyai-config`, the same [[push-before-incluster-build]] rule that governs
   BuildConfigs.

## Risks and known unknowns

1. ADR-0534 notes four documented upstream 3.5.0-ea.2 operator bugs already found in this operand
   (via ADR-0108/WP-10) - the baseline health check in Step 1 may resurface one of them even
   without any change on this WP's part. Record rather than silently work around.
2. `trustyai-config`'s health-check Job must run in a namespace the LMEvalJob's own NetworkPolicy
   allows querying from (same pattern as `models`) - verify before assuming.

## Status updates (once live-verified)

- ADR-0534 stays `Accepted` regardless of this WP's outcome; this WP's own `State` moves to `Done`
  once Steps 1-3 are live-verified and the checklist above passes.
- **2026-09-02 - Done.** All three steps executed and live-verified on demo222 the same day the
  brief was authored. Commits: `b44be5e7` (brief + ADR acceptance), `9a7a5120` (the
  `trustyai-config` scaffold - chart, `-d0`/`-d1` Applications, Ansible role, Makefile wiring,
  shared `ansible/tasks/report_lmevaljobs.yml` extracted from the `models` precheck), `690892da`
  (the double-TLS repair of the LM-Eval gate that Step 1's non-regression check exposed - see Live
  findings #1), `5cb5bde9` (closure). Verified live: `Ready=True`/`TrustyAIReady=True` on
  `zuno-dsc`, a fresh `qwen36-27b-instruct-mmlu` LMEvalJob back to `Complete/Succeeded`, and
  `zuno-trustyai-config-d0/-d1` Synced/Healthy. WP-108/WP-109 then filled the scaffold and closed
  the same day; ADR-0534 ended the day `Implemented`.
