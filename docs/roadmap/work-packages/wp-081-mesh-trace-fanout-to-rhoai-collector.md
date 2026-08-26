# WP-081: Fan mesh traces out to RHOAI's collector

- **State:** Not started.
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

_To be filled during implementation._

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
