# WP-078: Enable RHOAI monitoring metrics (Prometheus MonitoringStack, ThanosQuerier, Alerting)

- **State:** Done (live-verified 2026-08-26). The `MonitoringStack`, `ThanosQuerier` and
  Alertmanager this WP configures are Running in `redhat-ods-monitoring` - verified in the course
  of WP-079, whose own live check found the full metrics+traces stack up with 0 CrashLoopBackOff.
- **ADRs:** ADR-0522 (Implemented)
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

## Status updates

- ADR-0522 → `Implemented`. The gate this section used to state in the future tense ("stays
  `Proposed` until WP-079/WP-080 also land and verify") was met on 2026-08-26: WP-079 (traces) and
  WP-080 (Perses/Route/Dashboard) both closed `Done (live-verified)`, and WP-080 carried the ADR
  to `Implemented`. This WP closed the metrics half of that acceptance criteria.
- This brief lagged that closure until 2026-08-27 - it still read "live verification pending"
  and annotated `ADR-0522 (Proposed)` while the stack it configures had been live for a day.
  Nothing caught it: `platform/docs/check_docs.py` validates the ADR body/index pair only, and
  never reads a WP's `**State:**`.
