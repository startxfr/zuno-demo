# ADR-0523: Dual-export traces into the RHOAI monitoring stack

- **Status:** Implemented (live-verified 2026-08-26 via WP-081/WP-082 - real Envoy and vLLM
  spans searchable in RHOAI's Tempo, `zuno-monitoring`'s pipeline unchanged and still receiving
  the same traces). One caveat: `gpt-oss-20b` carries the correct spec but is unscheduled on a
  pre-existing GPU-node capacity problem, so only qwen's vLLM spans are proven - see WP-082.
- **Target:** v0.5
- **Date:** 2026-08-26
- **Decision owners:** Zuno Demo architecture team

## Context

[ADR-0522](0522-enable-openshift-ai-monitoring-stack-side-by-side.md) brought RHOAI's own
monitoring stack live in `redhat-ods-monitoring` (MonitoringStack, TempoStack,
`OpenTelemetryCollector`, Perses - all conditions `True`), but deliberately scoped phase 1 to
zero application/telemetry-config changes. The predictable consequence, confirmed live by
WP-080: RHOAI's Tempo holds **zero traces**, because nothing sends it data. Two independent
root causes:

1. **Mesh spans go to the other stack.** The `Istio` CR's single `otel-tracing`
   extensionProvider (`gitops/charts/service-mesh/templates/istio.yaml`, enabled mesh-wide by
   `templates/telemetry.yaml`) points at `zuno-otel-collector-collector.zuno-monitoring:4317`.
2. **Workload pods are never auto-instrumented.** RHOAI ships an `Instrumentation` CR
   (`data-science-instrumentation`), but the OpenTelemetry Operator only injects into pods
   carrying an `instrumentation.opentelemetry.io/inject-<lang>` annotation, and none of this
   repo's model-serving templates (`gitops/charts/models/templates/`) set one.

ADR-0522's "Migration / evolution" section requires exactly this ADR: an explicit decision on
how (or whether) the two stacks connect. Two live findings constrain the mechanics:

- **Istio's Telemetry API honors a single tracing provider per rule** (verified against the
  live v1.30.3 CRD; multiple `tracing` entries without `match` have undefined semantics), so
  "add a second extensionProvider" is not a workable dual-export path.
- **RHOAI 3.5.0-ea.2's own `Instrumentation` CR names a nonexistent Service**: its endpoint is
  `data-science-collector.redhat-ods-monitoring.svc:4317`, but only the operator-suffixed
  `data-science-collector-collector` Service exists (verified live, twice). Referencing RHOAI's
  CR from pod annotations would inject a dead exporter endpoint; the CR is controller-owned, so
  patching it in place would be reconciled away.
- **RHOAI's collector cannot deliver to its own Tempo either** (found during WP-081's live
  verification): its `otlp/tempo` exporter dials the Tempo gateway on 4317, a port the Tempo
  Operator never exposes on the gateway Service (OTLP gRPC is `grpc-public=8090`) - every
  received batch dies in an i/o-timeout retry loop. Both in-place fixes are operator-reverted
  within seconds (the Monitoring controller re-renders the collector config; the Tempo Operator
  strips extra gateway Service ports), and no ServiceAccount in the cluster holds the
  openshift-tenancy write grant the gateway SARs against. Routing anything through RHOAI's
  collector is therefore a dead end on this build - full trail in WP-081.

## Decision

**Dual-export application traces into RHOAI's collector while keeping both stacks and the
existing `zuno-monitoring` pipeline byte-for-byte intact** (the first option ADR-0522
enumerated). Two independent, composable paths:

- **Mesh-level fan-out (WP-081):** Envoy keeps its single `otel-tracing` provider pointed at
  `zuno-otel-collector`; that collector's `traces` pipeline gains a second exporter,
  `otlp/rhoai`, forwarding a copy of every span straight to RHOAI's Tempo **gateway**
  (`tempo-data-science-tempostack-gateway...:8090`) using the documented RHOSDT pattern -
  `bearertokenauth` with the collector's own ServiceAccount token, `X-Scope-OrgID:
  redhat-ods-monitoring`, service-ca TLS - plus a repo-owned `zuno-rhoai-tempo-traces-write`
  ClusterRole/Binding for the tenant write (nothing else in the cluster holds it). RHOAI's
  broken collector is bypassed, and everything involved is repo-owned, so no RHOAI operator can
  revert it. The service-mesh chart and `Istio` CR are untouched, so the Grafana/zuno-Tempo
  path ([ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md),
  [ADR-0413](0413-consolidate-grafana-dashboards-into-six-platform-views.md)) cannot regress.
- **Workload-level auto-instrumentation (WP-082):** a repo-owned `Instrumentation` CR
  (`zuno-models-instrumentation`, `zuno-ai-run`) pointing at the **platform** collector
  (`zuno-otel-collector-collector.zuno-monitoring:4317`) - whose WP-081 fan-out carries the
  spans on to RHOAI's Tempo with the gateway auth an in-process SDK cannot do, and both Tempo
  stacks get the workload spans - referenced via `instrumentation.opentelemetry.io/inject-sdk`
  annotations on all three model workloads. `inject-sdk` (env-only injection) rather than `inject-python`: the RH vLLM image
  already ships opentelemetry-sdk 1.43.0 + `opentelemetry-semantic-conventions-ai` (verified in
  the running pod), and a `PYTHONPATH` sitecustomize carrying the operator's older SDK is an
  avoidable risk on GPU pods. vLLM's native tracing is activated by its `--otlp-traces-endpoint`
  flag, added to both LLM templates from the same values key - deliberately not read from the
  injected env, since the webhook's `failurePolicy: Ignore` means injection may silently skip
  and model startup must not depend on it.

All application-originated spans (Envoy and in-process alike) therefore reach RHOAI's Tempo
through the single authenticated `otlp/rhoai` egress in `zuno-otel-collector`; W3C
trace-context propagation correlates mesh and workload spans across both Tempos.

## Operational considerations

100% sampling on both paths (matching the existing mesh-wide `randomSamplingPercentage: 100`
and RHOAI's `sampleRatio: "1.0"`) is a demo-cluster choice; RHOAI's Tempo retention is 48h
against its dedicated S3 bucket (WP-079). Both paths are values-gated
(`collector.rhoaiTraceExport.enabled`, `tracing.enabled`) so either export can be disabled
without template surgery. Verification is trace-driven, not condition-driven: a real inference
call must produce a non-empty result from RHOAI Tempo's search API before this ADR is marked
`Implemented`.

## Migration / evolution

The corrected-endpoint `Instrumentation` CR exists solely because RHOAI's is broken; when a
later RHOAI release fixes `data-science-instrumentation`'s endpoint, `zuno-models-instrumentation`
can be retired in favor of cross-namespace references to RHOAI's CR. The further unification
options ADR-0522 listed (shared S3 backend, Perses dashboard migration, retiring a stack) remain
undecided and would need another ADR.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Consequences,
Security considerations, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0522](0522-enable-openshift-ai-monitoring-stack-side-by-side.md) - phase 1; its
  Migration/evolution section mandates this decision.
- [ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md) and
  [ADR-0413](0413-consolidate-grafana-dashboards-into-six-platform-views.md) - the
  `zuno-monitoring` pipeline this ADR copies from without modifying.
- [ADR-0521](0521-route-local-model-traffic-through-maas.md) - established the
  `LLMInferenceService` `spec.annotations` pod-template propagation path WP-082 reuses.
