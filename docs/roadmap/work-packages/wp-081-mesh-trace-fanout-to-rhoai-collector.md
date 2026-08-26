# WP-081: Fan mesh traces out to RHOAI's collector

- **State:** In progress (pushed, awaiting live verification).
- **ADRs:** ADR-0523 (To be implemented)
- **Depends on:** WP-079 (RHOAI traces stack live), WP-080 (diagnosed the zero-traces root causes)
- **Related:** WP-082 (workload-level path, independent), ADR-0029/ADR-0413 (the zuno-monitoring
  pipeline this must not regress)

## Goal

Make MaaS Gateway/Envoy spans reach RHOAI's Tempo. Envoy sidecars mesh-wide already export
every span to `zuno-otel-collector` (`zuno-monitoring`) via the single `otel-tracing`
extensionProvider; add an `otlp/rhoai` exporter to that collector's `traces` pipeline so a copy
of every span is also forwarded to
`data-science-collector-collector.redhat-ods-monitoring.svc.cluster.local:4317`. The fan-out
lives in the collector - not the mesh - because Istio's Telemetry API honors only a single
tracing provider per rule (ADR-0523); the service-mesh chart and `Istio` CR stay untouched.

## Why not a second extensionProvider

That was the originally-prescribed shape. Verified against the live v1.30.3 CRD: `providers` is
effectively single-valued per tracing rule, and multiple `tracing` list entries without `match`
have undefined/last-wins semantics - a silent way to lose the existing `zuno-monitoring` export
that this repo's Grafana dashboards depend on. Collector-level fan-out is the standard OTel
pattern and leaves the proven path byte-for-byte identical.

## What changed

- `gitops/charts/observability/templates/opentelemetrycollector.yaml`: new `otlp/rhoai`
  exporter appended to the `traces` pipeline - straight to
  `tempo-data-science-tempostack-gateway...:8090` with `bearertokenauth/rhoai` (SA token),
  `X-Scope-OrgID: redhat-ods-monitoring` and service-ca TLS (see "Live finding" for why not
  RHOAI's collector), all gated on `collector.rhoaiTraceExport.enabled`. Metrics pipeline
  deliberately untouched (RHOAI's metrics side is Prometheus-scrape-shaped, not OTLP-push).
- New `gitops/charts/observability/templates/rbac-rhoai-traces.yaml`:
  `zuno-rhoai-tempo-traces-write` ClusterRole (+Binding for
  `zuno-monitoring/zuno-otel-collector-collector`) - the Tempo-operator-documented
  openshift-mode tenant-write rule.
- `gitops/charts/observability/values.yaml`: `collector.rhoaiTraceExport.enabled: false`
  (chart default false, matching the chart's all-default-false convention).
- `gitops/apps/observability/application-d1.yaml`: enables it inline next to
  `collector.enabled`. `helm template` verified: gate off renders byte-identical to before.
- `gitops/charts/openshift-ai/values.yaml`: DSCI traces retention canonicalized to `48h0m0s`
  (see "Live finding" item 5).
- `ansible/roles/openshift_ai/tasks/reconcile.yml`: header's `make d0` claim corrected to
  `make d1`; deliberate-non-action comment documenting the two operator-reverted fix attempts.

## Live finding: RHOAI's collector→Tempo hop has never worked, and can't be fixed in place

First verification attempt: the fan-out deployed clean (collector CR carried `otlp/rhoai`, new
pod healthy), a real embedding call returned 200 - and RHOAI's Tempo search still returned zero
traces. The debugging trail, all confirmed live:

1. **Spans DID arrive at RHOAI's `data-science-collector`** - whose own `otlp/tempo` exporter
   then error-looped `dial tcp <gateway-ClusterIP>:4317: i/o timeout`. The RHOAI-generated
   `tempo-data-science-tempostack-gateway` Service exposes ONLY `grpc-public=8090`,
   `internal=8081`, `public=8080`; 4317 exists solely on the distributor Service, whose
   NetworkPolicy admits only gateway pods. RHOAI 3.5.0-ea.2's trace pipeline can never have
   worked end-to-end.
2. **Fix attempt A - patch the collector's exporter endpoint to `:8090`** (via a new
   reconcile.yml task, `make d1 reconcile openshift-ai`): applied, then reverted by the
   Monitoring controller within seconds (it re-renders `spec.config`; unlike the TempoStack
   `resources.total` WP-079 patches, which it never revisits).
3. **Fix attempt B - append a `4317 -> grpc-public(8090)` port to the gateway Service**: applied
   (`changed`), stripped by the Tempo Operator within seconds.
4. **Also discovered: no ServiceAccount in the cluster holds the tenant-write grant**
   (`create` on `tempo.grafana.com/redhat-ods-monitoring`, resourceName `traces`) the
   openshift-mode gateway SARs against - not even RHOAI's own collector SA (it never gets far
   enough to need it). Third defect in the same pipeline, after the Instrumentation CR's
   nonexistent-Service endpoint (ADR-0523).
5. Incidental catch: the first reconcile run was blocked by latent WP-079 drift -
   `DSCInitialization`'s `traces.storage.retention: 48h` normalizes to `48h0m0s` in the stored
   CR, so ArgoCD saw permanent OutOfSync and the app-wait timed out. Fixed by canonicalizing
   the chart value; and reconcile.yml's header claimed a `make d0 reconcile openshift-ai` form
   that doesn't exist (openshift-ai is DAY1_RUN) - both corrected here.

**Final design**: bypass RHOAI's collector entirely. `zuno-otel-collector`'s `otlp/rhoai`
exporter goes straight to the Tempo **gateway** on 8090 with the documented RHOSDT pattern -
`bearertokenauth` (the pod's own SA token), `X-Scope-OrgID: redhat-ods-monitoring`, service-ca
TLS - plus a repo-owned `zuno-rhoai-tempo-traces-write` ClusterRole/Binding granting the
tenant write. Fully repo-owned, nothing for RHOAI's operators to fight. Consequence for WP-082:
its Instrumentation endpoint targets the platform collector (which fans out here), NOT RHOAI's
- so both Tempo stacks receive the workload spans. reconcile.yml keeps a deliberate-non-action
comment so nobody re-attempts the two reverted fixes.

## Verification checklist

1. ⬜ `oc get opentelemetrycollector zuno-otel-collector -n zuno-monitoring -o yaml` shows the
   `otlp/rhoai` exporter in the `traces` pipeline; new collector pod logs clean (no export
   errors against `data-science-collector-collector:4317`).
2. ⬜ Trigger a real embedding call (`oc exec deploy/rag-service -n zuno-data` → POST
   `http://embeddings-predictor.zuno-ai-run.svc:8080/v1/embeddings`), then search RHOAI's Tempo
   (`tempo-data-science-tempostack-gateway` route,
   `/api/traces/v1/redhat-ods-monitoring/tempo/api/search`, OpenShift bearer token): non-empty
   `traces` array with Envoy/istio-proxy-originated spans.
3. ⬜ Regression: the same call still produces a trace in `zuno-monitoring`'s Tempo (existing
   Grafana path intact).

## Status updates

_None yet._
