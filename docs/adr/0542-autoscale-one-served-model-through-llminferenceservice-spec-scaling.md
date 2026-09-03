# ADR-0542: Autoscale a served model through LLMInferenceService spec.scaling

- **Status:** Implemented
- **Target:** v0.7
- **Date:** 2026-09-02 (amended 2026-09-03 after the live apply)
- **Decision owners:** Zuno Demo architecture team

## Context

Nothing on this platform autoscales. Every served model is pinned: the four
`LLMInferenceService`s render `replicas: {{ minReplicas }}` with `minReplicas: 1`, and the
`maxReplicas` value sitting beside it in `gitops/charts/models/values.yaml` has never reached a
CR — it is carried and ignored. There is no `HorizontalPodAutoscaler` anywhere in the repo.
ADR-0318 installed the Custom Metrics Autoscaler (KEDA) operator ahead of any consumer, and it
has had **zero** `ScaledObject`s since; `gitops/apps/custom-metrics-autoscaler/application-d1.yaml`
says so in its own comment. The LeaderWorkerSet operator is installed with no LWS object. The
RHOAI dashboard's workload-variant-autoscaler logs "No active VariantAutoscalings found".

A capability review of the 43 never-instantiated CRDs on this cluster surfaced
`llmd.ai/v1alpha1 VariantAutoscaling` as the obvious candidate to close that gap. Two live
findings redirected the decision:

- **The CRD is deprecated by its own operand.** Every read returns, from the API server:
  *"VariantAutoscaling is deprecated and will be removed in a future release. Migrate to the
  annotation-based path (add llm-d.ai/managed=true to your HPA or ScaledObject)."* Hand-authoring
  it would be adopting a deprecated API on the day of adoption.
- **`LLMInferenceService.spec.scaling` exists and is the supported authoring surface.** Its schema
  is `{minReplicas, maxReplicas (required), wva: {hpa, keda, variantCost}}`, and
  `kserve-llmisvc-manager-role` holds CRUD on `llmd.ai/variantautoscalings`, `keda.sh/scaledobjects`
  and `autoscaling/horizontalpodautoscalers`. The controller *creates* the autoscaling object from
  it. The CRD still gets exercised — correctly.

The constraint that bounds the whole decision is capacity, and it is not the hardware. Both GPU
nodes advertise `nvidia.com/gpu: 0` with MIG slices only; cluster-wide that is 4 × 24GB and
2 × 48GB, against consumers that leave exactly one 24GB slice physically free. But
`ResourceQuota/zuno-ai-run-gpu-cap` is **saturated** — `requests.nvidia.com/mig-1g.24gb` 3/3 and
`mig-2g.48gb` 2/2 (read live). **Today no model in `zuno-ai-run` can reach two replicas at all.**

## Decision

1. **Author `spec.scaling`, never a raw `VariantAutoscaling`.** The deprecation warning is
   recorded verbatim in `gitops/charts/models/values.yaml` so the choice is not silently
   revisited.
2. **`gpt-oss-20b` is the only model that carries it, at `minReplicas: 1, maxReplicas: 1`.**
   `min == max` is deliberate and not a placeholder: the controller must still create its
   autoscaling object, which is the entire point — the workload-variant-autoscaler gets its first
   object, KEDA gets its first `ScaledObject`, the dashboards populate — while nothing can scale
   into a slice that does not exist. Zero quota exposure.
3. **`spec.scaling` and `spec.replicas` are rendered mutually exclusively.** Which one the
   controller honours when both are set is not knowable from the CRD schema, so the template
   emits exactly one. The ambiguity is designed out rather than discovered in production, and
   `scaling.enabled: false` is a one-value rollback to the previous behaviour.
4. **Raising `maxReplicas` is out of scope and is not a values edit.** It requires first raising
   `ResourceQuota/zuno-ai-run-gpu-cap` from 3 to 4, which spends the last physically free 24GB
   slice on the cluster and leaves **zero rolling-update surge headroom** — after which every
   24GB-model rollout hits `ProgressDeadlineExceeded` unless surge is handled explicitly. That is
   a separate, separately-approved change.
5. **`wva` is mandatory, carries exactly one mechanism, and that mechanism is `keda`.** The CRD's
   own CEL requires `has(self.wva)` and exactly one of `hpa`/`keda` inside it. `keda` because
   ADR-0318's Custom Metrics Autoscaler install has had zero `ScaledObject`s since it landed and
   this is its first consumer; `hpa` would have left that gap open. Amended 2026-09-03:
   the first attempt shipped `wva: {}`, which is not the same thing (see Operational
   considerations).
6. **The `ClusterTriggerAuthentication` is a prerequisite RHOAI names but does not ship, and this
   platform must author it.** KServe reads `triggerAuthName`/`triggerAuthKind` from RHOAI's
   `inferenceservice-config` ConfigMap (`autoscaling-wva-controller-config`) and stamps an
   `authenticationRef` to cluster-scoped `ai-inference-keda-thanos` onto every `ScaledObject` it
   derives from `spec.scaling`. No such object exists on a stock install. Without it the
   `ScaledObject` is created and is permanently `Ready=False`
   (`bearer token=<empty> is required when bearer auth is enabled`) and KEDA never creates the
   HPA — so `spec.scaling` alone does not deliver a working autoscaler. It is authored in
   `gitops/charts/custom-metrics-autoscaler` (the d1 operand slice), not in the models chart:
   cluster-scoped auth for any KEDA consumer is chart-level plumbing, not model-specific.

## Non-goals

Raising the GPU quota; autoscaling any other model (`qwen36-27b-instruct` and `qwen35-9b-wesh`
sit on the full 48GB tier; `qwen35-9b` is half ADR-0536's failover-drill pair and is pinned off
the wesh node by a required anti-affinity; `embeddings` is rag-service's hard query-path
dependency and is a plain `InferenceService` with no `spec.scaling` at all); tuning `wva.keda`'s
*behaviour*, which is meaningless while `min == max` — note that its **presence** is not a
tuning knob but a CRD requirement and a real decision, see decision 5.

## Operational considerations

- **The eliminations are as load-bearing as the choice.** `gpt-oss-20b` is not the best candidate
  among several — it is the only one, and the reasons the other four are excluded are each
  independent and structural. Re-deriving that list before extending this to a second model is
  cheaper than discovering it from a stuck rollout.
- **A quota at its ceiling is invisible in the CR.** `spec.scaling` will happily carry
  `maxReplicas: 2` and simply never reach it, reporting healthy. The `models` precheck therefore
  prints the autoscaling object counts and the GPU quota's used/hard together, so the two facts
  cannot be read apart.
- Which of `spec.replicas` and `spec.scaling` wins when both are present is deliberately left
  undiscovered — see decision 3. If a future change needs the answer, read the rendered
  Deployment's `spec.replicas`, do not infer it.
- `gitops/apps/custom-metrics-autoscaler/application-d1.yaml` authors no `ScaledObject` and should
  not: the first one on this cluster is created *by KServe*. It does author the
  `ClusterTriggerAuthentication` that `ScaledObject` references — see decision 6.
- **`helm template` is not validation on a CEL-validated CRD.** The first attempt rendered
  `wva: {}`, which disappears entirely through Helm's `with`; `helm template` accepted the result
  and the API server rejected it (`spec.scaling: Invalid value: wva is required when scaling is
  configured`), pinning the whole `models` Application until it was fixed. Any chart change
  touching a CRD with CEL rules needs `oc apply --dry-run=server`, not a render.
- **"The object exists" and "the object works" are different checks.** The live apply created both
  autoscaling objects and looked successful for nine hours while the `ScaledObject` sat
  `Ready=False` on the missing trigger auth and no HPA existed at all. Counting objects is what
  made that look green, so the `custom-metrics-autoscaler` precheck now reports each
  `ScaledObject`'s `Ready` condition and message, not just a count.
- **Two gaps are known, recorded, and deliberately not closed** — both moot while `min == max`.
  The `VariantAutoscaling` reports `MetricsAvailable=False`/`MetricsMissing` because the
  operand-managed `workload-variant-autoscaler-saturation-scaling-config` carries only a `default`
  key and the controller logs *"Saturation scaling config not loaded yet for namespace"*; and
  `AcceleratorNotResolved`, because WVA cannot infer an accelerator from the pod's generic
  `nvidia.com/gpu.present: "true"` nodeSelector. Replica metrics are emitted regardless, so KEDA
  can scale; only accelerator-specific saturation metrics are withheld.

## Migration / evolution

Executed by [WP-121](../roadmap/work-packages/wp-121-llminferenceservice-spec-scaling.md).
Future: a real scale-up demonstration, which is gated on the quota decision in decision 4 and on
GPU capacity this cluster does not currently have; and `wva` tuning once a model genuinely has a
range to move in.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Consequences,
Security considerations, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0318](0318-install-custom-metrics-autoscaler-and-jobset-operators.md) - the KEDA install
  whose zero-consumer gap this discharges.
- [ADR-0351](0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md),
  [ADR-0414](0414-consolidate-zuno-ai-run-into-three-tiered-mig-predictors.md) - the MIG topology
  and predictor tiering that make the headroom what it is.
- [ADR-0536](0536-live-node-failover-drill-for-qwen-model-fallback.md) - the failover pair
  deliberately excluded from autoscaling.
- [ADR-0201](0201-complete-the-openshift-ai-maas-governance-plane-integration.md) - its documented
  rollout hazard is the surge consequence decision 4 defers.
- [ADR-0538](0538-adopt-rhoai-35-workload-surfaces-mlflow-kueue-trainingjobs.md) - the sibling
  effort adopting other RHOAI 3.5 surfaces.
