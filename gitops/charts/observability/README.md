# observability

Referenced by `gitops/apps/observability/application-d0.yaml`
(operator.enabled: `Namespace` + `OperatorGroup` + `Subscription` for the
Red Hat build of OpenTelemetry operator) and `application-d1.yaml`
(collector.enabled: the `zuno-monitoring` Namespace + the shared
`OpenTelemetryCollector` instance) - same operator/operand `-d0`/`-d1`
split as `nfd`/`nvidia-gpu`/`openshift-ai` (ADR-0312).

ADR-0029: instruments model usage, cost and distributed traces. The
Collector exports traces to both `debug` (log-based sanity check) and
`otlp/tempo` (`gitops/charts/tempo`'s `TempoMonolithic`, queried by
`gitops/charts/kiali`'s Kiali instance). See
`ansible/roles/observability/README.md`.
