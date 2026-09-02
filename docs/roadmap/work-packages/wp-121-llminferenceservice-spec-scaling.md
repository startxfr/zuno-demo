# WP-121: Autoscaling objects from LLMInferenceService spec.scaling

- **State:** Repo work merged (2026-09-02) — the chart change is in and renders both branches
  correctly; the live apply that creates the first autoscaling object has not been run
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
  `wva: {}`), carrying the reasoning for `min == max`, the quota arithmetic, and the deprecation
  warning verbatim.
- `gitops/charts/models/templates/llminferenceservice-gptoss.yaml` — renders **either**
  `spec.scaling` **or** `spec.replicas`, never both.
- `ansible/roles/models/tasks/precheck.yml` — reports the three autoscaling object counts and the
  GPU `ResourceQuota`'s used/hard together.
- `gitops/apps/custom-metrics-autoscaler/application-d1.yaml` — comment updated to record that it
  correctly stays empty, because the first `ScaledObject` is created by KServe, not authored there.

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

## Remaining

1. Apply live (`make d2 install models`) and confirm the controller creates its object:
   `VariantAutoscaling` and/or `ScaledObject` appear, and
   `workload-variant-autoscaler-controller-manager` stops logging "No active VariantAutoscalings
   found".
2. Read the rendered Deployment's `spec.replicas` to record which field the controller honoured —
   the one live question ADR-0542 deliberately designed out rather than guessed.
3. Not in scope, and not to be done casually: raising the quota 3 → 4 for a real scale-up demo.
   That spends the last free 24GB slice and leaves zero surge headroom.

## Verification

```bash
helm template m gitops/charts/models | grep -A3 'name: gpt-oss-20b' # spec.scaling, no spec.replicas
helm template m gitops/charts/models --set gptOssModel.scaling.enabled=false  # the rollback path
oc get variantautoscaling,scaledobject,hpa -n zuno-ai-run
oc get resourcequota zuno-ai-run-gpu-cap -n zuno-ai-run -o jsonpath='{.status}'
oc logs deploy/workload-variant-autoscaler-controller-manager -n redhat-ods-applications --tail=20
make d2 check models
```
