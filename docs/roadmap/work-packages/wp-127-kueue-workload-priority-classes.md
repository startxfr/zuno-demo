# WP-127: order zuno-ai-run's batch Jobs by reusing the existing PriorityClass hierarchy

- **State:** Done (2026-09-03)
- **ADRs:** ADR-0545 (decision 2, started here - amended 2026-09-03 by this WP's own findings)
- **Depends on:** WP-117 (Done, 2026-09-03 - GPU-MIG ResourceFlavor + ClusterQueue quota,
  LocalQueue and namespace enrolment for `zuno-ai-run`)
- **Related:** [ADR-0542](../../adr/0542-autoscale-one-served-model-through-llminferenceservice-spec-scaling.md)
  (the saturated-quota measurement motivating this WP),
  [ADR-0321](../../adr/0321-delegate-kueue-lifecycle-to-the-red-hat-build-of-kueue-operator.md)

> **Recentered 2026-09-03.** Originally scoped around a new Kueue `WorkloadPriorityClass` to
> protect agent-serving inference from batch delay. Both premises were corrected by this WP's own
> research (see ADR-0545 decision 2's amendment): `LLMInferenceService` predictors are not
> Kueue-managed at all (only `BatchJob` is an integrated framework), so Kueue cannot delay
> something it never admits; and Kueue already derives `Workload` queueing priority from the
> pod's standard `priorityClassName`, so a new CRD would duplicate a working mechanism. The real,
> corrected goal below.

## Goal

`zuno-ai-run`'s batch Jobs (LMEval MMLU + its cache-prefetch, `job-garak-security`,
`job-garak-smoke`, `job-ragas-eval`, `job-zuno-day2-stresstest-*`) all admit through the same
`default` `ClusterQueue`/`LocalQueue` under a saturated GPU quota (`mig-1g.24gb` 3/3,
`mig-2g.48gb` 2/2, WP-121). Live inspection (`oc get workload -n zuno-ai-run -o yaml`) found that
today's quality/security-gate Jobs - MMLU, the real `garak-security` scan, RAGAS - carry **no**
`priorityClassName` and admit at `spec.priority: 0`, while the `day2-stresstest-*` availability
drills carry `priorityClassName: zuno-platform-weak` and admit at `spec.priority: 1` - one notch
**above** the evaluation/security gates. This was not a deliberate choice; it is what happens when
only one Job family was ever given a `priorityClassName`. This WP designs the fix by reusing the
existing `PriorityClass` hierarchy, with no new CRD.

## What landed

1. **Design.** A new `.Values.kueue.priorityClassName` field, added to `gitops/charts/models` and
   `gitops/charts/trustyai-config` alongside the existing `.Values.kueue.queueName`, gates
   `priorityClassName: zuno-workload-default` (`value: 100`,
   `gitops/charts/admin-context/templates/priorityclass-workload-default.yaml`) on three Jobs -
   above `zuno-platform-weak` (`1`, day2-stresstest, unchanged) and well below
   `zuno-platform-important`/`-critical` (`10000`/`1000000`, reserved for platform infra):
   - `gitops/charts/models/templates/job-lmeval-cache-prefetch.yaml`
   - `gitops/charts/trustyai-config/templates/job-garak-security.yaml`
   - `gitops/charts/trustyai-config/templates/job-ragas-eval.yaml`

   **`lmevaljob.yaml` (the `LMEvalJob` CR itself) cannot carry this field.** Verified live via
   `oc explain lmevaljob.spec.pod` (the same discipline `lmevaljob.yaml`'s own header comment
   already follows - "every field... confirmed real via `oc explain`"): the CRD's `spec.pod`
   exposes exactly `affinity`, `container`, `securityContext`, `sideCars`, `volumes` - no
   `priorityClassName` pass-through exists. The operator gives no way to set the MMLU evaluation
   run's own pod priority from this chart; only its cache-prefetch companion Job (a plain
   `batch/v1 Job`, fully controllable) can be prioritized. Recorded as a real CRD limitation, not
   routed around by guessing at an undocumented field.

   **Ships empty by default**, same convention and for the same reason as `kueue.queueName`
   (`gitops/charts/trustyai-config/values.yaml`'s own comment): these Jobs carry
   `Replace=true,Force=true`, so ANY rendered-metadata change deletes and recreates them (see the
   DiskPressure warning below) - flipping the value is a deliberate, watched operator action, not
   something this WP's commit triggers by itself on the next ArgoCD sync.

   **Deliberately not touched:** `job-garak-smoke.yaml` (a lightweight smoke check, `0` stays
   appropriate) and the `day2-stresstest-*` Jobs (`zuno-platform-weak` is already the right tier
   for an availability drill, not a quality/security gate).

2. **`priorityClassName` is set on the pod template** (`spec.template.spec.priorityClassName`),
   not the Job's own metadata - unlike `kueue.x-k8s.io/queue-name`, which must sit on the Job's
   `metadata.labels` for Kueue's `BatchJob` integration to read it before suspending the Job,
   `priorityClassName` is a standard Kubernetes pod-spec field and Kueue reads the *pod template's*
   value to set the admitted `Workload`'s `spec.priority` - putting it on the Job's own metadata
   would be inert.

3. **`helm template` validated clean** on both `gitops/charts/models` and
   `gitops/charts/trustyai-config` at their default values (the new field renders nothing, no
   diff at all - proving the ship-empty default is inert) and with
   `--set kueue.priorityClassName=zuno-workload-default` (the rendered diff is exactly the three
   new `priorityClassName: zuno-workload-default` lines, nothing else moved).

4. **Before/after comparison** (live `spec.priority` values, `oc get workload -n zuno-ai-run`,
   2026-09-03):

   | Job family | Before | After |
   |---|---|---|
   | `job-lmeval-cache-prefetch` | `0` | `100` |
   | `job-garak-security` | `0` | `100` |
   | `job-ragas-eval` | `0` | `100` |
   | LMEval MMLU (the `LMEvalJob` CR itself) | `0` | `0` (unchanged - CRD limitation, see above) |
   | `job-garak-smoke` (unchanged) | `0` | `0` |
   | `job-zuno-day2-stresstest-*` (unchanged) | `1` | `1` |

   Under contention, the prefetch/security/RAGAS batch Jobs now outrank a stresstest drill for
   admission into the saturated GPU quota, which was not true before this WP. The MMLU evaluation
   run's own pod priority is unchanged - a gap this WP found but could not close within the
   `LMEvalJob` CRD's exposed schema; closing it would need either an upstream feature or a
   different mechanism entirely (e.g. a namespace-wide default `PriorityClass`), out of scope
   here.

## What NOT to touch (out of scope for this WP)

- **No live application.** This WP's scope is the design plus a clean `helm template` render; no
  `oc apply`/ArgoCD sync was performed. Applying it live is a follow-up, to be scoped as its own
  WP if wanted.
- **No new `WorkloadPriorityClass` CRD** - superseded by the recentered design (decision 2's
  amendment).
- **No change to the `ClusterQueue`/`ResourceFlavor` quota** WP-117/ADR-0538 decision 3
  established - this WP only orders admission within the existing quota.
- **No mechanism for protecting agent-serving from GPU contention** - `LLMInferenceService`
  predictors are outside Kueue entirely; that would need a native-Kubernetes mechanism
  (`ResourceQuota`/pod-preemption), logged as a future candidate, not designed here.

## Acceptance checks

- `helm template` on `gitops/charts/models` and `gitops/charts/trustyai-config` - PASS, diff
  limited to the three `priorityClassName` additions (default values render no diff at all).
- `helm lint` - clean on both charts.
- `oc apply --dry-run=server` (2026-09-03, non-mutating - server-side dry-run persists nothing),
  scoped to the three changed templates individually: the API server accepted
  `priorityClassName: zuno-workload-default` as valid and resolved the `PriorityClass` (no
  "not found" error) on all three; the only rejection was `field is immutable` on
  `job-lmeval-cache-prefetch` (all 3 model instances) and `job-garak-security`/`job-ragas-eval`
  against their already-live Job objects - confirming, not contradicting, this brief's own
  documented need for `Replace=true` on any future live rollout. No new problem surfaced.
- The before/after table above is grounded in real, live `oc get workload` output, not simulated.
- No live `Workload` or `LocalQueue` object was actually changed by this WP.

## Operator / human follow-up (not executable by the model)

Decide whether to apply this design live and whether the day2-stresstest/quality-gate ordering it
encodes matches actual business priority (this WP proposed a default, not a mandated ranking).

**Live application is not the low-risk change it looks like.** All three target Jobs carry
`argocd.argoproj.io/sync-options: Replace=true,Force=true` (a Job's `spec.template` is immutable,
so ANY change to it - this `priorityClassName` addition included - forces ArgoCD to delete and
recreate the Job, re-pulling its image). `gitops/charts/trustyai-config/values.yaml`'s own
`kueue.queueName` comment documents that exactly this pattern, on the models chart's prefetch
Jobs, took a control-plane node from 85% image-filesystem usage to `DiskPressure` in 22 seconds on
2026-09-03 (garak's image alone is 4.22 GiB) - see the `diskpressure-master-cascades-into-mesh`
incident record, status still open as of this WP. Live nodes were confirmed clear of
`DiskPressure` before this WP touched these files (`oc get nodes`, all `False`), but a future
live-apply WP must stage the three Job recreations (not all at once) and be run while someone is
watching node disk, exactly as the existing `queueName` precedent already requires for these same
Jobs.

## Status updates (then re-run check_docs.py)

`State: Done` reflected in this brief and its `docs/roadmap/implementation-roadmap.md` tracker
row together. ADR-0545 itself stays `Accepted` - decision 2 is designed, not yet live, and
decisions 1/3 (WP-126/WP-128) are tracked separately.

## Out of scope / deferred

Live application (future WP, on request). `WorkloadPriorityClass`/`Cohort`/`AdmissionCheck`
(ADR-0545 decision 5 - not adopted for lack of a driving need). Protecting agent-serving from
batch GPU contention (native-Kubernetes mechanism, future ADR candidate, not Kueue).
