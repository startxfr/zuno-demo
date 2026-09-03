# WP-121: Autoscaling objects from LLMInferenceService spec.scaling

- **State:** Done (2026-09-03) — live-verified end to end: `ScaledObject` `Ready=True`/`Active=True`
  and `keda-hpa-gpt-oss-20b-kserve-keda` created with `ScalingActive=True: ValidMetricFound`
- **ADRs:** [ADR-0542](../../adr/0542-autoscale-one-served-model-through-llminferenceservice-spec-scaling.md)
- **Depends on:** none
- **Related:** [ADR-0318](../../adr/0318-install-custom-metrics-autoscaler-and-jobset-operators.md)
  (the KEDA install this gives its first consumer),
  [ADR-0538](../../adr/0538-adopt-rhoai-35-workload-surfaces-mlflow-kueue-trainingjobs.md)

## Goal

Give the platform its first autoscaling object, without giving it anywhere to scale.

Nothing here autoscales today: four `LLMInferenceService`s pinned at `replicas: 1`, a
`maxReplicas` value that has never reached a CR, no HPA anywhere, KEDA installed with zero
`ScaledObject`s since ADR-0318, and the workload-variant-autoscaler logging "No active
VariantAutoscalings found". Live-confirmed before the change: `VariantAutoscaling=0`,
`ScaledObject=0`, `HorizontalPodAutoscaler=0` in `zuno-ai-run`.

## What landed

- `gitops/charts/models/values.yaml` — a `gptOssModel.scaling` block (`enabled: true`,
  `wva: {keda: {}}`), carrying the reasoning for `min == max`, the quota arithmetic, and the
  deprecation warning verbatim. It shipped as `wva: {}` first; see finding 3.
- `gitops/charts/models/templates/llminferenceservice-gptoss.yaml` — renders **either**
  `spec.scaling` **or** `spec.replicas`, never both.
- `ansible/roles/models/tasks/precheck.yml` — reports the three autoscaling object counts and the
  GPU `ResourceQuota`'s used/hard together.
- `gitops/apps/custom-metrics-autoscaler/application-d1.yaml` +
  `gitops/charts/custom-metrics-autoscaler/templates/clustertriggerauthentication.yaml` — the
  `ClusterTriggerAuthentication` KServe requires and RHOAI does not ship, plus its ServiceAccount,
  long-lived token Secret and `cluster-monitoring-view` binding. See finding 4 — this is what
  actually made the ScaledObject work.
- `ansible/roles/custom_metrics_autoscaler/tasks/precheck.yml` — reports each `ScaledObject`'s
  `Ready` condition and message, not just a count. See finding 5.

## Two things this work package is careful about

**It authors `spec.scaling`, not `VariantAutoscaling`.** The API server returns a deprecation
warning on every read of that CRD, pointing at the annotation-based path. `spec.scaling` is the
supported surface, and the controller creates the `VariantAutoscaling`/`ScaledObject` from it —
so the CRD is exercised without adopting a deprecated API.

**`maxReplicas` stays 1, and that is the finding, not a shortcut.**
`ResourceQuota/zuno-ai-run-gpu-cap` is saturated at `mig-1g.24gb` 3/3 and `mig-2g.48gb` 2/2, so
no model in the namespace can reach two replicas at all. `gpt-oss-20b` is not the best of several
candidates — it is the only one:

| Model | Why it cannot autoscale |
|---|---|
| `qwen36-27b-instruct` | 48GB tier, 2/2 used |
| `qwen35-9b-wesh` | 48GB tier, 2/2 used |
| `qwen35-9b` | half ADR-0536's failover-drill pair; required anti-affinity pins it off the wesh node |
| `embeddings` | rag-service's hard query-path dependency, and a plain `InferenceService` with no `spec.scaling` |

## Live findings

1. **Applied `2026-09-02T23:14:35Z`; the controller created both objects.**
   `VariantAutoscaling/gpt-oss-20b-kserve-va` and `ScaledObject/gpt-oss-20b-kserve-keda`, both
   owned by the `LLMInferenceService`. The workload-variant-autoscaler reconciles it every 30s and
   no longer logs "No active VariantAutoscalings found". ✅
2. **`spec.scaling` is what the controller honoured** — `Deployment/gpt-oss-20b-kserve` reports
   `spec.replicas=1`, `ready=1`. This is the one live question ADR-0542 designed out rather than
   guessed, now answered by reading it rather than inferring it. ✅
3. **`wva: {}` is not a valid empty default.** The CRD's CEL requires `has(self.wva)` and exactly
   one of `hpa`/`keda`; an empty map disappears through Helm's `with`, so `helm template` rendered
   it happily and the API server rejected the CR (`wva is required when scaling is configured`),
   pinning the whole `models` Application. Fixed to `wva: {keda: {}}` — `keda` because ADR-0318's
   install is the thing this WP exists to give a consumer. **A chart change touching a
   CEL-validated CRD needs `oc apply --dry-run=server`, not a render.**
4. **The `ScaledObject` existed and had never worked — for nine hours.** It sat `Ready=False`:
   `ScaledObjectCheckFailed: ... bearer token=<empty> is required when bearer auth is enabled`,
   and KEDA had created **no HPA at all**. KServe stamps an `authenticationRef` to cluster-scoped
   `ClusterTriggerAuthentication/ai-inference-keda-thanos` — a name it reads from RHOAI's
   `inferenceservice-config` (`autoscaling-wva-controller-config`) — and **RHOAI ships no such
   object**. Authored here; the ScaledObject then went `Ready=True`/`Active=True` and
   `keda-hpa-gpt-oss-20b-kserve-keda` appeared with `ScalingActive=True: ValidMetricFound`. ✅
5. **KEDA does not re-reconcile a `ScaledObject` when its TriggerAuthentication appears.** After
   the auth object landed, the stale `Ready=False` persisted, and a metadata annotation did not
   dislodge it (generation-based predicate). Deleting the `keda-operator` pod forced the
   re-reconcile. Worth knowing: on a fresh install ordering makes this invisible, but on any
   retrofit the fix looks like it failed when it has actually succeeded.
6. **Counting objects is what made a broken state look green.** Both autoscaling objects existed
   the whole time. The `custom-metrics-autoscaler` precheck now reports the `Ready` condition and
   message per ScaledObject, so "exists" and "works" cannot be read apart again.
7. **`spec.wva.variantCost: "10.0"` appears live but is not in git** — a CRD default. ArgoCD
   reports `Synced`; no drift, no `ignoreDifferences` needed.

## Known limitations, deliberately not closed

Both are moot while `min == max == 1` — no scaling decision can be applied regardless.

- `VariantAutoscaling` reports `MetricsAvailable=False`/`MetricsMissing`, and the controller logs
  *"Saturation scaling config not loaded yet for namespace, skipping model"*. The operand-managed
  `workload-variant-autoscaler-saturation-scaling-config` carries only a `default` key; RHOAI would
  revert an edit to it.
- `AcceleratorNotResolved`: WVA cannot infer an accelerator from the pod's generic
  `nvidia.com/gpu.present: "true"` nodeSelector. Replica metrics are still emitted — which is why
  KEDA's HPA works — and only accelerator-specific saturation metrics are withheld. Both available
  fixes (a narrower nodeSelector, or a label on a controller-generated VA) cost more than they buy.

Still out of scope, still not to be done casually: raising the quota 3 → 4 for a real scale-up
demo. That spends the last free 24GB slice and leaves zero surge headroom.

## Verification

```bash
helm template m gitops/charts/models | grep -A3 'name: gpt-oss-20b' # spec.scaling, no spec.replicas
helm template m gitops/charts/models --set gptOssModel.scaling.enabled=false  # the rollback path

# finding 3 - render is not validation on a CEL-validated CRD
helm template cma gitops/charts/custom-metrics-autoscaler \
  --set triggerAuthentication.enabled=true --set kedaController.enabled=true \
  | oc apply --dry-run=server -f -

# the acceptance signal - all three must hold
oc get scaledobject gpt-oss-20b-kserve-keda -n zuno-ai-run \
  -o jsonpath='{range .status.conditions[*]}{.type}={.status}: {.reason}{"\n"}{end}'   # Ready=True
oc get hpa keda-hpa-gpt-oss-20b-kserve-keda -n zuno-ai-run                            # 1/1, MIN/MAX 1/1
oc get deploy gpt-oss-20b-kserve -n zuno-ai-run -o jsonpath='{.spec.replicas}'         # 1, unmoved

oc get variantautoscaling,scaledobject,hpa -n zuno-ai-run
oc get resourcequota zuno-ai-run-gpu-cap -n zuno-ai-run -o jsonpath='{.status}'   # still 3/3, 2/2
make d1 check custom-metrics-autoscaler
make d2 check models
```

Note: `make d2 check models` currently reports "models is NOT installed" because
`InferenceService/embeddings` is `Progressing` on an unrelated KServe webhook `FailedCreate`. That
predates this work package and is not a regression from it.
