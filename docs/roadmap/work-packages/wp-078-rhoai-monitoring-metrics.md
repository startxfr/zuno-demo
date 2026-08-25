# WP-078: Enable RHOAI monitoring metrics (Prometheus MonitoringStack, ThanosQuerier, Alerting)

- **State:** Repo change done, live verification pending (operator step).
- **ADRs:** ADR-0522 (Proposed)
- **Depends on:** ADR-0331 (Implemented — fixed `monitoring.namespace`, the prerequisite this
  builds on)
- **Related:** WP-079 (traces, next), WP-080 (Perses/Route/dashboard verification)

## Goal

Populate `DSCInitialization.spec.monitoring.metrics`/`.alerting` so RHOAI provisions its own
Prometheus-based `MonitoringStack`, `ThanosQuerier` and Alertmanager in `redhat-ods-monitoring` —
the first of three side-by-side monitoring increments (ADR-0522).

## Why

`redhat-ods-monitoring` has been empty since ADR-0331 landed: `spec.monitoring.metrics` was left
`{}`. The live `default-dsci` status already names the exact cause
(`MonitoringStackAvailable: False`, reason `MetricsNotConfigured`). No operator install is
needed — Cluster Observability Operator, backing `MonitoringStack`/`ThanosQuerier`, is already
installed cluster-wide as an RHOAI 3.5 dependency.

## What changed

- `gitops/charts/openshift-ai/values.yaml`: `cluster-ods.DSCInitialization.spec` now sets
  `monitoring.metrics.storage` (`size: 25Gi`, `retention: 15d`) and `monitoring.alerting: {}`.
  `alerting` requires `metrics.storage` to be set — the CRD itself validates this — so both land
  together. No other file changes: `gitops/apps/openshift-ai/application-d1.yaml` already sets
  `DSCInitialization.enabled: true` and inherits this chart default.

## Verification checklist (operator step — ask before running)

- `make d1 reconcile openshift-ai` (or let ArgoCD self-heal sync).
- `oc get dsci default-dsci -o jsonpath='{.status.conditions}'` shows `MonitoringStackAvailable`,
  `ThanosQuerierAvailable`, `AlertingAvailable` all `True`.
- `oc get monitoringstack,thanosquerier -n redhat-ods-monitoring` and `oc get pods -n
  redhat-ods-monitoring` show Prometheus/Alertmanager/Thanos-querier `Running`.

## Status updates (once live-verified)

- ADR-0522 stays `Proposed` until WP-079/WP-080 also land and verify — this WP alone only closes
  the metrics half of ADR-0522's acceptance criteria.
