# perses

ADR-0551/ADR-0552/WP-138: duplicates `zuno-monitoring`'s Grafana dashboard
set as namespace-scoped `PersesDashboard`s on RHOAI's existing
`data-science-perses` instance (`perses.dev/v1alpha2`, Cluster Observability
Operator) - no server of our own, per ADR-0552 (an earlier attempt ran an
independent instance and broke RHOAI's own dashboards live, see ADR-0551's
dated correction note). Backed by three cluster-scoped
`PersesGlobalDatasource`s and surfaced in the OpenShift console via a COO
`UIPlugin` (`type: Dashboards`) - see `gitops/apps/perses/application-d1.yaml`
and `gitops/charts/perses/README.md`.

No `-d0`: the Cluster Observability Operator is already subscribed
cluster-wide by `ansible/roles/mesh_monitoring`'s own `-d0` apply
(`gitops/apps/mesh-monitoring/application-d0.yaml`) - this role only applies
the `-d1` Application. Additive to Grafana, not a replacement: Grafana's own
`gitops/apps/grafana` Applications are untouched. Additive to RHOAI's own
monitoring stack too: a new, distinctly-named ServiceAccount/Secret is
created inside `redhat-ods-monitoring` for Bearer auth, but nothing
RHOAI-owned is modified, deleted, or depended upon beyond reading its
`data-science-perses` label and one existing ConfigMap.

Depends on `mesh_monitoring` (the Cluster Observability Operator
Subscription) and RHOAI's `data-science-perses` instance being healthy
(ADR-0522/WP-080). WP-138 covers the three datasources, the `UIPlugin`, and
two pilot dashboards (`mesh-gateway`, `trustyai`); WP-139 adds the remaining
eight once that pattern is live-verified.
