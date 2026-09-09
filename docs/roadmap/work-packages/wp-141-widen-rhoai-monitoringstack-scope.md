# WP-141: Widen RHOAI's MonitoringStack to observe zuno-ai-run

- **State:** Done (2026-09-09 - live-verified end to end, 6 parts; 3
  known, separately-scoped gaps remain - see Status updates)
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
5. **The fix for the "Cluster"/"Models" tabs specifically** (ADR-0554's
   second dated correction note): `rhods-dashboard`'s "Observe & Monitor"
   tabs read exclusively from `PersesDatasource/cluster-prometheus-
   datasource`, which points at `thanos-querier.openshift-monitoring.svc`
   (`prometheus-k8s`+UWM) - a **third** Prometheus, not
   `data-science-monitoringstack` that parts 1-4 targeted. That stack
   already had full RBAC/CRD-group compatibility for KServe's PodMonitors;
   the only gap was NetworkPolicy - `networkpolicy-qwen.yaml` already
   admitted `openshift-monitoring`/`openshift-user-workload-monitoring`
   (ADR-0413, its comment wrongly called it "not actually needed", now
   corrected), `qwen35`/`gptoss`/`wesh` never did. Added the same admission
   to all three. This single asymmetry is why exactly one model
   (`qwen36-27b-instruct`) ever showed real data through this entire
   investigation, independent of parts 1-4.
6. **The fix for "LLM Traffic"/"LLM Utilization"/"LLM Performance"**
   (ADR-0554's third dated correction note): these three tabs DO read
   `data-science-monitoringstack` (parts 1-4's target), but every one of
   their PromQL queries filters on `exported_namespace=~"$namespace"`
   and/or groups by `k8s_pod_name` - labels part 4's PodMonitor never
   produced (plain `namespace`/`pod` from standard k8s SD). Fixed by
   adding two `relabelings` entries to that same PodMonitor, copying
   `__meta_kubernetes_namespace`/`__meta_kubernetes_pod_name` into those
   exact names at scrape time.

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
- [x] Real, nonzero traffic reaches RHOAI's own Thanos: after `make d3
  stresstest` (224/248 checks passed - real bulk interactions through the
  agents), `sum(increase(kserve_vllm:request_success_total[1h])) by
  (llm_isvc_name)` queried against `data-science-thanos-querier-route`
  showed real counts for 3/4 models (`qwen36-27b-instruct` ~6,
  `qwen35-9b-wesh` ~13, `gpt-oss-20b` ~13; `qwen35-9b` 0 - not routed to
  this run, a business-routing outcome, not a metrics gap).
- [x] The dashboard's OWN data source (`cluster-prometheus-datasource` ->
  `thanos-querier.openshift-monitoring.svc`, found via the browser's
  Network tab - not `data-science-monitoringstack`) now returns all 4
  models: `up{namespace="zuno-ai-run",job=~".*kserve.*"}` shows all 4 pods
  at `up=1`, and `count(group(kserve_vllm:num_requests_running) by
  (model_name, namespace))` - the exact "Deployed models" panel query -
  returns `4`, queried directly against that same datasource's upstream.
  Literal browser screenshot pending the user's own reload.
- [x] `git status` on every `zuno-monitoring`/Grafana/Kiali-owning chart
  shows no changes from this work.
- [x] "LLM Traffic"/"LLM Utilization"/"LLM Performance" tabs
  (`data-science-prometheus-datasource`) return real series, not empty
  results, for the exact panel queries: `kserve_vllm:num_requests_running
  {exported_namespace=~"zuno-ai-run"}` returns all 4 models (0 before part
  6); the "Throughput (req/s)" panel query showed 14 nonzero points across
  the 30 minutes spanning a `make d3 stresstest` run, queried directly
  through the same browser proxy path
  (`/perses/api/proxy/.../data-science-prometheus-datasource/...`).

## Status updates

- **2026-09-09 — Done.** All 6 parts written and live-verified on
  `demo333`. Parts 1-4 (below) target `data-science-monitoringstack` and
  are real, correct fixes for that stack - but the user, after a hard
  browser refresh and a private window, still saw only 1 of 5 models.
  Root cause (found from the browser's own Network tab, not guessed):
  `rhods-dashboard`'s "Cluster"/"Models" tabs read exclusively from
  `PersesDatasource/cluster-prometheus-datasource`
  (`config.default: true`), which points at
  `thanos-querier.openshift-monitoring.svc` - the **platform's own**
  Thanos (`prometheus-k8s`+UWM), a third Prometheus instance parts 1-4
  never touched. That stack already had full RBAC/CRD-group
  compatibility for KServe's PodMonitors (no `data-science-
  monitoringstack`-style landmine there); the only gap was NetworkPolicy,
  and only for 3 of the 4 models - `networkpolicy-qwen.yaml` already had
  the needed admission from a pre-existing ADR-0413 rule (whose own
  comment incorrectly called it unnecessary), the other three never did.
  Part 5 (same commit family) added the missing admission and is what
  actually resolved the "Cluster"/"Models" tabs. `helm lint`/`helm
  template`/`ansible-playbook --syntax-check`/`check_workload_hardening.py`/
  `check_docs.py` all pass throughout.
- **2026-09-09, later the same day — Part 6 added.** After part 5, the
  user confirmed "Cluster"/"Models" showed all 4 models but reported the
  remaining three tabs ("LLM Traffic"/"LLM Utilization"/"LLM Performance")
  still showed "No data" even after a fresh stresstest produced real,
  moving traffic. These three DO read `data-science-monitoringstack`
  (parts 1-4's actual target) - so parts 1-4 should have sufficed, and
  didn't. Root cause: every PromQL query on those three dashboards filters
  on `exported_namespace=~"$namespace"` and/or groups by `k8s_pod_name`,
  labels part 4's PodMonitor never produced (plain `namespace`/`pod` from
  standard k8s SD - `exported_namespace`/`k8s_pod_name` is what an OTel
  Collector k8s-semconv pipeline produces instead, which this PodMonitor
  deliberately bypasses). Fixed by adding two relabeling rules to copy
  those labels at scrape time. Also found, live-confirmed, and
  deliberately left unfixed as separate/out-of-scope: the "Usage" tab
  needs Limitador metrics (`authorized_hits_total` etc.) that Limitador
  doesn't emit at all on this cluster (a Limitador config gap, not a
  discovery/RBAC/NetworkPolicy problem); "GPU utilization" and "Error
  rate" panels need `accelerator_gpu_utilization`/
  `inference_model_request_error_total`, which exist in no Prometheus on
  this cluster at all (no DCGM exporter, no EPP metrics emitter deployed).
  See ADR-0554's "Known out-of-scope gaps" section.
