# perses

ADR-0551/ADR-0552/WP-138: a second dashboard layer duplicating
`zuno-monitoring`'s Grafana dashboard set onto Perses (`perses.dev/v1alpha2`,
Cluster Observability Operator), physically split by application namespace
instead of Grafana's own template-filtered consolidation (ADR-0413). Grafana
is not modified, reduced, or replaced - see `gitops/charts/grafana/README.md`
for the dashboard set this duplicates.

**Reuses RHOAI's existing `data-science-perses` instance** (ADR-0552) rather
than running an independent one. An earlier attempt (ADR-0551's original
decision 2) ran a second, independent `Perses` server instance and broke
RHOAI's own dashboards live for ~14 minutes: `PersesDashboard`/
`PersesDatasource`/`PersesGlobalDatasource` resources with no
`instanceSelector` set - exactly how every one of RHOAI's own resources is
configured - resolve against **any** Perses instance on the cluster
(standard Kubernetes `LabelSelector` semantics, not a bug). See ADR-0551's
dated correction note and ADR-0552 for the full incident and redesign.

Referenced by a single `gitops/apps/perses/application-d1.yaml` - no `-d0`
and no server CR of any kind.

## What this chart renders

- Three cluster-scoped `PersesGlobalDatasource`s targeting
  `data-science-perses` (`instanceSelector.matchLabels:
  {platform.opendatahub.io/part-of: monitoring}`), the same three backends
  `gitops/charts/grafana/templates/datasource-*.yaml` already uses:
  `prometheus` (thanos-querier, Bearer-authenticated via a **new**
  ServiceAccount/Secret this chart creates in `redhat-ods-monitoring` -
  `templates/serviceaccount-prometheus-reader.yaml` - reusing RHOAI's own
  `prometheus-web-tls-ca` ConfigMap for TLS rather than duplicating it),
  `mesh-prometheus` (mesh-monitoring's own MonitoringStack, no auth),
  `tempo` (ADR-0029's TempoMonolithic, no auth - not RHOAI's own, separately
  auth'd Tempo). All three use the `plugin.spec.proxy: {kind: HTTPProxy,
  spec: {url, secret?}}` shape, copied from RHOAI's own live, working
  `PersesDatasource` examples - not the unverified `directUrl` shape the
  first attempt guessed.
- One `UIPlugin` (`dashboards`, `type: Dashboards`) giving Perses a real
  navigation entry inside the OpenShift console - unaffected by the
  ADR-0552 pivot; it also now surfaces RHOAI's own pre-existing dashboards,
  accepted as a harmless side effect.
- Two pilot `PersesDashboard`s (WP-138), each in the application namespace
  it actually observes, targeting `data-science-perses` via the same
  `instanceSelector`:

  | File | Namespace | Duplicates (Grafana uid) |
  |---|---|---|
  | `dashboard-mesh-gateway.yaml` | `zuno-mesh` | `zuno-mesh-gateway` |
  | `dashboard-trustyai.yaml` | `zuno-ai-run` | `zuno-trustyai` |

  WP-139 adds the remaining eight dashboards once this pattern is
  live-verified - see ADR-0551's mapping table for every dashboard's target
  namespace, including the five that stay `platform`-scoped in
  `zuno-monitoring` (no single owning application namespace).

## What this chart does NOT touch

No RHOAI-owned object in `redhat-ods-monitoring` is modified, deleted, or
depended upon beyond reading `data-science-perses`'s label and the
`prometheus-web-tls-ca` ConfigMap's contents. The only new footprint inside
that namespace is this chart's own, distinctly-named
`zuno-perses-prometheus-reader` ServiceAccount/Secret/ClusterRoleBinding -
never RHOAI's own identities or secrets.

## Known unknowns (WP-138's live verification is the confirmation gate)

Panel/query/datasource plugin kind names and the `plugin.spec.proxy` shape
are confirmed against RHOAI's own live, `Available: true` Perses resources
on this same cluster - not guessed, unlike the first attempt. What remains
genuinely unverified: whether `proxy.spec.secret` truly resolves relative to
the Perses server's own namespace (`redhat-ods-monitoring`) as inferred from
RHOAI's own examples, and the `ListVariable`/
`PrometheusLabelValuesVariable` template-variable plugin (no RHOAI example
to confirm against). See each template's own header comment. Grafana's
table `transformations` (column merge/rename) and its cross-dashboard link
dropdown have no confirmed Perses equivalent used here - both are
documented, deliberate simplifications, not silent gaps.
