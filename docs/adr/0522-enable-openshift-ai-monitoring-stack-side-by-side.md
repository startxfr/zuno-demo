# ADR-0522: Enable OpenShift AI's built-in monitoring stack, side-by-side with the existing observability stack

- **Status:** Implemented (live-verified 2026-08-26 via WP-078/WP-079/WP-080 - metrics, traces
  and Perses all live and healthy in `redhat-ods-monitoring`, fully side-by-side with
  `zuno-monitoring`, zero application code changes). Phase 2 (unifying the two stacks) is a
  separate, not-yet-started follow-up - see WP-080's "Phase 2" section.
- **Target:** v0.5
- **Date:** 2026-08-26
- **Decision owners:** Zuno Demo architecture team

## Context

`redhat-ods-monitoring` has existed since ADR-0331 (2026-08-13) reverted
`DSCInitialization.spec.monitoring.namespace` to RHOAI's own default to fix `dashboard`/Perses
reconciliation. The namespace itself has been empty ever since - no pods, no route. The live
`default-dsci`'s own `status.conditions` name the exact reason: `spec.monitoring.metrics: {}` is
empty and `spec.monitoring.traces` is absent, so `MonitoringStackAvailable`, `TempoAvailable`,
`OpenTelemetryCollectorAvailable`, `AlertingAvailable` and `PersesAvailable` are all `False`
("Metrics not configured in DSCI CR" / "Traces not configured in DSCI CR"). Every operator this
needs - Cluster Observability Operator, Red Hat build of OpenTelemetry, Tempo Operator, Grafana
Operator - is already installed cluster-wide as an RHOAI 3.5 dependency (`oc get csv -A`); this
is purely a configuration gap, not a missing-operator gap.

Separately, `zuno-monitoring` already runs a hand-deployed Grafana + `TempoMonolithic` + OTel
Collector stack ([ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md),
consolidated by [ADR-0413](0413-consolidate-grafana-dashboards-into-six-platform-views.md)),
observing the Zuno application stack (agent-bff, rag-service, mcp-gateway, etc.). RHOAI's own
monitoring stack, once configured, observes RHOAI-managed workloads (KServe/vLLM model serving,
AI Pipelines, GPU) via its own auto-instrumentation - a distinct, currently-unobserved surface.

## Decision

Populate `DSCInitialization.spec.monitoring.metrics` and `.traces` so RHOAI provisions its own
Prometheus-based `MonitoringStack`, `ThanosQuerier`, Alertmanager, `TempoStack`/`TempoMonolithic`,
`OpenTelemetryCollector` and Perses dashboards in `redhat-ods-monitoring`, scoped to RHOAI-managed
workloads only, running fully **side-by-side** with - not replacing, not sharing a backend with -
the existing `zuno-monitoring` stack:

- **Metrics:** `metrics.storage` (25Gi, 15d retention) and `alerting` enabled, backed by RHOAI's
  own `MonitoringStack`/`ThanosQuerier`.
- **Traces:** `traces.storage.backend: s3`, against a dedicated bucket
  (`zuno-demo-rhoai-traces`), credentials wired through the same
  Vault -> `ExternalSecret` -> Secret chain `gitops/charts/aap/templates/
  externalsecret-hub-s3.yaml` already established for Automation Hub's S3 storage.
- **Access:** both a dedicated Route to Perses/Tempo (mirroring `gitops/charts/grafana`'s
  oauth-proxy Route pattern) and RHOAI Dashboard's built-in "Observe" tab, which surfaces the
  same data automatically once metrics/traces are configured.
- **Scope, explicitly:** no change to any application code or OTel SDK/exporter configuration.
  `zuno-monitoring` keeps exclusive responsibility for application-level telemetry in this phase.

Tracked by WP-078 (metrics), WP-079 (traces), WP-080 (Perses/Route/Dashboard verification).

## Operational considerations

Verification is condition-driven, not guesswork: `oc get dsci default-dsci -o
jsonpath='{.status.conditions}'` must show `MonitoringStackAvailable`, `ThanosQuerierAvailable`,
`AlertingAvailable`, `TempoAvailable`, `OpenTelemetryCollectorAvailable` and `PersesAvailable`
all `True` before this ADR is marked `Implemented`. Traces credential rotation follows the
existing Vault-seed pattern (`ansible/confidential.yml` + `make d0 install vault`), same as every
other S3-backed component in this repo.

## Migration / evolution

This ADR deliberately does **not** decide how (or whether) the two observability stacks get
unified. A later ADR must make that call explicitly, choosing among (non-exhaustive): dual-
exporting application traces into RHOAI's `OpenTelemetryCollector` alongside `zuno-monitoring`'s;
pointing both `Tempo` instances at a shared S3 backend; migrating `zuno-monitoring`'s Grafana
dashboards onto RHOAI's Perses; or retiring one stack in favor of the other. Until such an ADR
lands, both stacks are independently owned and independently operated.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Consequences,
Security considerations, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0331](0331-revert-openshift-ai-to-the-default-applications-namespace.md) - fixed
  `monitoring.namespace`, the prerequisite this ADR builds on.
- [ADR-0328](0328-separate-the-openshift-ai-control-plane-from-ai-build-and-run-workload-namespaces.md) -
  superseded namespace model; the platform/build/run split this ADR's namespace choices remain
  consistent with.
- [ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md) and
  [ADR-0413](0413-consolidate-grafana-dashboards-into-six-platform-views.md) - the existing
  `zuno-monitoring` stack this ADR sits beside without modifying.
