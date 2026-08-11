# mesh-monitoring

Referenced by `gitops/apps/mesh-monitoring/application-d0.yaml`
(operator.enabled: `Namespace` + `OperatorGroup` + `Subscription` for the
Red Hat Cluster Observability operator) and `application-d1.yaml`
(monitoring.enabled: a `MonitoringStack` plus the `ServiceMonitor`/`PodMonitor`
scraping `istiod` and the mesh's Envoy sidecars, all in `zuno-mesh`) - same
operator/operand `-d0`/`-d1` split as `observability`/`tempo`/`kiali`
(ADR-0312).

Exists because this repo has no OpenShift User Workload Monitoring enabled
anywhere (a cluster-admin-level change, out of this GitOps repo's scope), so
`gitops/charts/kiali`'s Kiali instance has no other Prometheus-compatible
metrics source for its traffic graph and health views. `zuno-mesh` itself is
owned by `gitops/charts/namespaces`, not this chart.
