# perses

ADR-0551/WP-138: a second, independent dashboard layer duplicating
`zuno-monitoring`'s Grafana dashboard set onto Perses (`perses.dev/v1alpha2`,
Cluster Observability Operator), physically split by application namespace
instead of Grafana's own template-filtered consolidation (ADR-0413). Grafana
is not modified, reduced, or replaced - see `gitops/charts/grafana/README.md`
for the dashboard set this duplicates.

Referenced by a single `gitops/apps/perses/application-d1.yaml` - no `-d0`:
the Cluster Observability Operator is already subscribed cluster-wide by
`gitops/apps/mesh-monitoring/application-d0.yaml`; a second Subscription
here would fight that Application for ownership of the same operator.

## What this chart renders

- One `Perses` server instance (`perses`, `zuno-monitoring`, label
  `dashboards: perses`) - a single instance for the whole cluster, mirroring
  Grafana's own single-instance model. Namespace scoping is achieved by
  where each `PersesDashboard`/`PersesGlobalDatasource` lives plus
  `instanceSelector`, not by running one Perses per namespace.
- Three cluster-scoped `PersesGlobalDatasource`s, the same three backends
  `gitops/charts/grafana/templates/datasource-*.yaml` already uses:
  `prometheus` (thanos-querier, authenticated via the Perses pod's own
  `client.kubernetesAuth` rather than Grafana's static-secret Bearer
  header), `mesh-prometheus` (mesh-monitoring's own MonitoringStack, no
  auth), `tempo` (distributed traces, no auth).
- One `UIPlugin` (`dashboards`, `type: Dashboards`) giving Perses a real
  navigation entry inside the OpenShift console - unlike Grafana, which has
  no console presence at all today (only its own oauth-proxied Route).
- Two pilot `PersesDashboard`s (WP-138), each in the application namespace
  it actually observes:

  | File | Namespace | Duplicates (Grafana uid) |
  |---|---|---|
  | `dashboard-mesh-gateway.yaml` | `zuno-mesh` | `zuno-mesh-gateway` |
  | `dashboard-trustyai.yaml` | `zuno-ai-run` | `zuno-trustyai` |

  WP-139 adds the remaining eight dashboards once this pattern is
  live-verified - see ADR-0551's mapping table for every dashboard's target
  namespace, including the five that stay `platform`-scoped in
  `zuno-monitoring` (no single owning application namespace).

## Known unknowns (WP-138's live verification is the confirmation gate)

Perses's dashboard model is typed CUE/JSON (`panels`/`layouts`/`queries` as
structured objects), unlike Grafana's opaque JSON blob - the two pilot
dashboards above are a real per-panel translation, not a copy-paste, and
several pieces are best-effort against upstream Perses's documented schema
rather than confirmed against this cluster's specific COO 1.5.2-bundled
Perses version (no Perses instance exists anywhere on this cluster as of
this chart's authoring): panel/query/datasource plugin kind names, the
`client.kubernetesAuth` in-cluster-token mechanism for the `prometheus`
datasource, how the `UIPlugin` discovers which `Perses` instance(s) to
render, and the `ListVariable`/`PrometheusLabelValuesVariable` template
variables. See each template's own header comment for the specific caveat.
Grafana's table `transformations` (column merge/rename) and its
cross-dashboard link dropdown have no confirmed Perses equivalent used here
- both are documented, deliberate simplifications, not silent gaps.
