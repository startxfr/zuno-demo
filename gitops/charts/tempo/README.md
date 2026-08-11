# tempo

Referenced by `gitops/apps/tempo/application-d0.yaml` (operator.enabled:
`Namespace` + `OperatorGroup` + `Subscription` for the Red Hat build of the
Tempo operator) and `application-d1.yaml` (tempo.enabled: a demo-scale
`TempoMonolithic` in `zuno-monitoring`) - same operator/operand `-d0`/`-d1`
split as `observability`/`nfd`/`nvidia-gpu`/`openshift-ai` (ADR-0312).

Stores traces exported by `gitops/charts/observability`'s Collector
(`otlp/tempo` exporter) and queried by `gitops/charts/kiali`'s Kiali
instance. `zuno-monitoring` itself is owned by `gitops/charts/namespaces`, not
this chart.
