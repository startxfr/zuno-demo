# mesh_monitoring

Installs the Red Hat Cluster Observability Operator and a `MonitoringStack`
(`mesh-monitoring`, `zuno-mesh` namespace) plus the `ServiceMonitor`/
`PodMonitor` scraping `istiod` and the mesh's Envoy sidecars, via
`gitops/apps/mesh-monitoring/application-d0.yaml` (operator) and
`application-d1.yaml` (instance) - see `gitops/apps/README.md` and
`gitops/charts/mesh-monitoring/README.md`.

Exists because this repo has no OpenShift User Workload Monitoring enabled
anywhere (a cluster-admin-level change, out of scope for this GitOps repo),
so the `kiali` role's Kiali instance has no other Prometheus-compatible
metrics source for its traffic graph and health views. Depends on
`service_mesh` (scrapes `istiod` and mesh sidecars).
