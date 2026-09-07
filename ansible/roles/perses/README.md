# perses

ADR-0551/WP-138: a Perses server (`perses.dev/v1alpha2`, Cluster
Observability Operator) duplicating `zuno-monitoring`'s Grafana dashboard
set as namespace-scoped `PersesDashboard`s, backed by three cluster-scoped
`PersesGlobalDatasource`s and surfaced in the OpenShift console via a COO
`UIPlugin` (`type: Dashboards`) - see `gitops/apps/perses/application-d1.yaml`
and `gitops/charts/perses/README.md`.

No `-d0`: the Cluster Observability Operator is already subscribed
cluster-wide by `ansible/roles/mesh_monitoring`'s own `-d0` apply
(`gitops/apps/mesh-monitoring/application-d0.yaml`) - this role only applies
the `-d1` Application. Additive to Grafana, not a replacement: Grafana's own
`gitops/apps/grafana` Applications are untouched.

Depends on `mesh_monitoring` (the Cluster Observability Operator
Subscription). WP-138 covers the server, the three datasources, the
`UIPlugin`, and two pilot dashboards (`mesh-gateway`, `trustyai`); WP-139
adds the remaining eight once that pattern is live-verified.
