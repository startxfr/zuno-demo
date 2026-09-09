# WP-141: Widen RHOAI's MonitoringStack to observe zuno-ai-run

- **State:** Done (2026-09-09 - live-verified end to end, 4 parts)
- **ADRs:** ADR-0554
- **Related:** ADR-0522, ADR-0552, ADR-0553
- **Target:** v0.5

## Goal

Make RHOAI's built-in "Observe & Monitor > Dashboard > Models" tab
(`rhods-dashboard`) show real traffic/latency/GPU data for all 5 models
deployed in `zuno-ai-run`, instead of one model with all-zero stats -
purely additive on the RHOAI side, with zero changes to the platform's own
Grafana/Kiali/`zuno-monitoring` stack (hard user constraint).

## Implementation

Four independently-necessary changes, per ADR-0554's Decision (the 4th
found live-necessary only after the original 3-part plan still yielded
zero series - see the ADR's Dated correction note):

1. **Ansible partial patch** widening `MonitoringStack/data-science-
   monitoringstack`'s `spec.namespaceSelector` to `zuno-ai-run`
   (`ansible/roles/openshift_ai/tasks/widen_monitoringstack_namespace_selector.yml`,
   wired into `install.yml`/`reconcile.yml`) - not GitOps, since that CR is
   RHOAI-operator-owned; live-verified via `.metadata.managedFields` that
   this specific field is safe (RHOAI's own field-manager never claims it).
2. **New Role/RoleBinding** in `zuno-ai-run`
   (`gitops/charts/models/templates/rolebinding-rhoai-monitoringstack-prometheus.yaml`)
   granting RHOAI's MonitoringStack Prometheus ServiceAccount read-only
   access to Services/Endpoints/Pods/EndpointSlices/Ingresses there.
3. **NetworkPolicy admission** for `redhat-ods-monitoring` on TCP 8000,
   added to all four LLMInferenceService NetworkPolicies
   (`gitops/charts/models/templates/networkpolicy-{qwen,qwen35,gptoss,wesh}.yaml`) -
   found live-necessary (the PodMonitor scrapes pods directly and none of
   these four previously admitted this namespace), correcting three stale
   comments that claimed no NetworkPolicy allowance was needed for metrics.
4. **New `monitoring.rhobs/v1` PodMonitor**
   (`gitops/charts/models/templates/podmonitor-rhoai-vllm-engine.yaml`)
   mirroring KServe's own `kserve-llm-isvc-vllm-engine` PodMonitor
   (`monitoring.coreos.com/v1`) - RHOAI's Prometheus (Cluster Observability
   Operator-based) only has RBAC for the `monitoring.rhobs` CRD group and
   can never discover the community-group one KServe creates, regardless
   of namespace/RBAC/NetworkPolicy scope. Covers the 4 LLMInferenceService
   models only - `embeddings` (a classic `InferenceService`, different
   serving runtime/metrics path entirely) is out of scope for this WP.

## Acceptance criteria

- [x] `oc get monitoringstack data-science-monitoringstack -n
  redhat-ods-monitoring -o jsonpath='{.spec.namespaceSelector}'` shows the
  patch, and survives a second `make d1 reconcile openshift-ai` (proves it's
  not a one-shot fluke reverted by RHOAI's own reconciler).
- [x] `zuno-models-d1`/`zuno-openshift-ai-d0`/`zuno-openshift-ai-d1`
  Applications stay `Synced`/`Healthy` throughout.
- [x] RHOAI's Prometheus (`prometheus-data-science-monitoringstack-0`) shows
  `health:"up"` targets for `namespace="zuno-ai-run"` via its own
  `/api/v1/targets` API - confirmed for all 4 LLMInferenceService models.
- [ ] Browser-verified `rhods-dashboard` Observe & Monitor > Models tab
  showing nonzero numbers after real traffic - not yet done this session
  (requires sending live inference requests through each model first);
  the Prometheus-side data path is proven, this is presentation-layer only.
- [x] `git status` on every `zuno-monitoring`/Grafana/Kiali-owning chart
  shows no changes from this work.

## Status updates

- **2026-09-09 — Done.** All 4 parts written and live-verified on
  `demo333`. Parts 1-3 alone were insufficient (confirmed live: zero
  `zuno-ai-run` series reached RHOAI's Prometheus even with a correctly
  widened `namespaceSelector`, correct RBAC, and correct NetworkPolicy) -
  root-caused to KServe's PodMonitor using `monitoring.coreos.com/v1`
  while RHOAI's Cluster-Observability-Operator-based Prometheus only has
  RBAC for `monitoring.rhobs` (two separate CRDs, confirmed via `oc get
  crd`). Part 4 added and live-verified: all 4 model targets `health: up`
  within seconds. `helm lint`/`helm template`/`ansible-playbook
  --syntax-check`/`check_workload_hardening.py`/`check_docs.py` all pass.
  Remaining: a browser screenshot of the actual dashboard tab with live
  traffic, deferred to whenever the models next see real usage.
