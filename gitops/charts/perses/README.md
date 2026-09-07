# perses

ADR-0551/ADR-0552/ADR-0553/WP-138: a second dashboard layer duplicating
`zuno-monitoring`'s Grafana dashboard set onto Perses (`perses.dev/v1alpha2`,
Cluster Observability Operator). Grafana is not modified, reduced, or
replaced - see `gitops/charts/grafana/README.md` for the dashboard set this
duplicates.

Two design pivots, both from live findings the same day (2026-09-07):

1. **Reuses RHOAI's existing `data-science-perses` instance** (ADR-0552)
   rather than running an independent one. An earlier attempt (ADR-0551's
   original decision 2) ran a second, independent `Perses` server instance
   and broke RHOAI's own dashboards live for ~14 minutes:
   `PersesDashboard`/`PersesDatasource`/`PersesGlobalDatasource` resources
   with no `instanceSelector` set - exactly how every one of RHOAI's own
   resources is configured - resolve against **any** Perses instance on the
   cluster (standard Kubernetes `LabelSelector` semantics, not a bug).
2. **Collocates every dashboard in `redhat-ods-monitoring`** (ADR-0553)
   rather than splitting them per application namespace (ADR-0551's
   original decision 1/6). Neither the OpenShift console (no consumer wired
   for the `UIPlugin`'s extension on this OCP release) nor a standalone
   Perses UI (Red Hat's `perses-rhel9` image ships without its bundled
   frontend) render anything visible on this cluster. The one path that
   does render real data - `rhods-dashboard`'s "Monitor & observe" tab - only
   shows dashboards from the `redhat-ods-monitoring` project, hardcoded
   (that app has no RBAC on `perses.dev` at all; it calls Perses's REST API
   directly against that fixed project name).

See ADR-0551's three dated correction notes, ADR-0552 and ADR-0553 for the
full incident/redesign history.

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
- One `UIPlugin` (`dashboards`, `type: Dashboards`) - kept deployed
  (harmless, forward-compatible) even though live investigation confirmed
  it has no console consumer on this OCP release. Not the working access
  path - see below.
- Two pilot `PersesDashboard`s (WP-138), both in `redhat-ods-monitoring`
  (ADR-0553), targeting `data-science-perses` via the same
  `instanceSelector`, named with a `zuno-` prefix to avoid any collision
  with RHOAI's own eight dashboards sharing that namespace:

  | File | Name | Duplicates (Grafana uid) |
  |---|---|---|
  | `dashboard-mesh-gateway.yaml` | `zuno-mesh-gateway` | `zuno-mesh-gateway` |
  | `dashboard-trustyai.yaml` | `zuno-trustyai` | `zuno-trustyai` |

  WP-139 adds the remaining eight dashboards once this pattern is
  live-verified - all also land in `redhat-ods-monitoring`, per ADR-0553.

## How to actually view these dashboards

Log into `rhods-dashboard` (RHOAI's own web app, a separate Route/login from
the OpenShift console) and open its "Monitor & observe" tab - the only
confirmed-working visual path on this cluster. There is no OpenShift
console nav entry (the `UIPlugin`'s extension has no consumer on this OCP
release) and no direct-Route UI (Red Hat's Perses image ships server-only).

## What this chart does NOT touch

No RHOAI-owned object in `redhat-ods-monitoring` is modified, deleted, or
depended upon beyond reading `data-science-perses`'s label and the
`prometheus-web-tls-ca` ConfigMap's contents. The only new footprint inside
that namespace is this chart's own, distinctly-named
`zuno-perses-prometheus-reader` ServiceAccount/Secret/ClusterRoleBinding and
its `zuno-`-prefixed `PersesDashboard`s - never RHOAI's own identities,
secrets, or dashboards.

## Known unknowns (WP-138's live verification is the confirmation gate)

Panel/query/datasource plugin kind names and the `plugin.spec.proxy` shape
are confirmed against RHOAI's own live, `Available: true` Perses resources
on this same cluster - not guessed, unlike the first attempt. What remains
genuinely unverified: whether `proxy.spec.secret` truly resolves relative to
the Perses server's own namespace (`redhat-ods-monitoring`) as inferred from
RHOAI's own examples, whether `rhods-dashboard`'s "Monitor & observe" tab
actually renders these dashboards once collocated (the reason for this
redesign, still to be confirmed by a real login), and the `ListVariable`/
`PrometheusLabelValuesVariable` template-variable plugin (no RHOAI example
to confirm against). See each template's own header comment. Grafana's
table `transformations` (column merge/rename) and its cross-dashboard link
dropdown have no confirmed Perses equivalent used here - both are
documented, deliberate simplifications, not silent gaps.
