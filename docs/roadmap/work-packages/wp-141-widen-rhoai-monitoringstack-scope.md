# WP-141: Widen RHOAI's MonitoringStack to observe zuno-ai-run

- **State:** Repo work merged (2026-09-09 - live verification pending)
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

Three independently-necessary changes, per ADR-0554's Decision:

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

## Acceptance criteria

- [ ] `oc get monitoringstack data-science-monitoringstack -n
  redhat-ods-monitoring -o jsonpath='{.spec.namespaceSelector}'` shows the
  patch, and survives a second `make d1 reconcile openshift-ai` (proves it's
  not a one-shot fluke reverted by RHOAI's own reconciler).
- [ ] `zuno-models-d1`/`zuno-openshift-ai-d0`/`zuno-openshift-ai-d1`
  Applications stay `Synced`/`Healthy` throughout.
- [ ] RHOAI's Prometheus (`prometheus-data-science-monitoringstack-0`) shows
  `health:"up"` targets for `namespace="zuno-ai-run"` via its own
  `/api/v1/targets` API.
- [ ] After sending real inference requests through each of the 5 models,
  `rhods-dashboard`'s Observe & Monitor > Models tab shows all 5 with
  nonzero request-rate/latency/GPU numbers (browser-verified).
- [ ] `git status` on every `zuno-monitoring`/Grafana/Kiali-owning chart
  shows no changes from this work; those dashboards spot-checked to still
  render identically.

## Status updates

- **2026-09-09 — Repo work merged.** All three parts written, `helm
  lint`/`helm template`/`ansible-playbook --syntax-check`/
  `check_workload_hardening.py`/`check_docs.py` all pass. Live verification
  (the acceptance criteria above) not yet run - the next `make d1 reconcile
  openshift-ai` + `make d2 install models` cycle on `demo333` closes this
  out.
