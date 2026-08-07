# observability

Referenced by `gitops/apps/observability/application-d0.yaml`
(operator.enabled: `Namespace` + `OperatorGroup` + `Subscription` for the
Red Hat build of OpenTelemetry operator) and `application-d1.yaml`
(collector.enabled: the `zuno-telemetry` Namespace + the shared
`OpenTelemetryCollector` instance) - same operator/operand `-d0`/`-d1`
split as `nfd`/`nvidia-gpu`/`openshift-ai` (ADR-0312).

ADR-0029: instruments model usage, cost and distributed traces. Installs
the collection path only - no long-term backend (Tempo/Prometheus
storage) is installed; the Collector's debug/log exporter is enough to
prove the pipeline for a demo. See `ansible/roles/observability/README.md`.
