# WP-138: Perses datasources and pilot dashboards (zuno-mesh-gateway, zuno-trustyai)

- **State:** Done (2026-09-07 - data layer live-verified correct; no
  visual rendering exists for these dashboards anywhere on this cluster,
  confirmed and accepted - see Status updates)
- **ADRs:** ADR-0551, ADR-0552, ADR-0553
- **Depends on:** none
- **Related:** WP-139 (translates the remaining eight dashboards once this
  pattern is live-verified); WP-080 (owns `data-science-perses` and
  `rhods-dashboard`'s "Monitor & observe" tab - the Perses instance and
  viewing surface this WP reuses read-only, see ADR-0552/ADR-0553)
- **Target:** v0.5
- **Estimated files touched:** ~8 files under `gitops/charts/perses/` and
  `gitops/apps/perses/`; 3 new objects (ServiceAccount, Secret,
  ClusterRoleBinding) plus 2 `PersesDashboard`s in `redhat-ods-monitoring`;
  0 existing Grafana or RHOAI files/objects modified.

> Execute this brief as a standalone task from the repository root.

## Goal

Duplicate two of `zuno-monitoring`'s ten Grafana dashboards - `mesh-gateway`
and `trustyai`, renamed `zuno-mesh-gateway`/`zuno-trustyai` - as
`PersesDashboard`s **in `redhat-ods-monitoring`**, on **RHOAI's existing
`data-science-perses` instance** (ADR-0552), backed by three shared
`PersesGlobalDatasource`s, viewable via `rhods-dashboard`'s "Monitor &
observe" tab (ADR-0553 - the only working visual path found on this
cluster). This proves the whole chain (datasource auth against a shared
instance, collocated placement, real rendering, panel translation) before
WP-139 scales it to the remaining eight dashboards. Grafana is not
modified; no RHOAI-owned resource is modified or deleted.

## Why this work is required

ADR-0551 decided to duplicate Grafana's dashboards onto Perses. Two live
findings the same day revised how:

1. Attempt 1 ran an independent second `Perses` server instance and broke
   RHOAI's own dashboards live (see Status updates) -
   `instanceSelector`-less resources (exactly how every RHOAI Perses
   resource is configured) match *any* Perses instance on the cluster, a
   standard Kubernetes `LabelSelector` behavior, not a bug. ADR-0552:
   reuse `data-science-perses` instead of running a second instance.
2. Attempt 2 (ADR-0552's design) applied and worked at the data layer, but
   live investigation found no working visual rendering path for
   namespace-scoped dashboards on this cluster: the OpenShift console's
   `/monitoring/dashboards` page has no consumer for the `UIPlugin`'s
   extension, and RHOAI's `data-science-perses-route` serves Perses's own
   image with no bundled frontend at all. The one path that does render
   real data - `rhods-dashboard`'s "Monitor & observe" tab - only shows
   dashboards from the `redhat-ods-monitoring` project (hardcoded, no
   `perses.dev` RBAC on that app - it calls Perses's REST API directly
   against that fixed project name). ADR-0553: collocate every dashboard
   there instead of splitting per application namespace.

## Repo changes

1. **`gitops/charts/perses/`** - no `templates/perses.yaml` (no server CR).
   Chart stays a single `-d1`-only Application (no operator Subscription -
   COO is already subscribed via
   `gitops/apps/mesh-monitoring/application-d0.yaml`).
2. `templates/serviceaccount-prometheus-reader.yaml` - a ServiceAccount
   (`zuno-perses-prometheus-reader`) + long-lived token Secret +
   ClusterRoleBinding to `cluster-monitoring-view`, in
   `redhat-ods-monitoring` (this is where RHOAI's own `PersesDatasource`s
   resolve their `proxy.spec.secret` references from, inferred from their
   live examples, confirmed live). Distinctly named to avoid any collision
   with RHOAI's own `cluster-prometheus-datasource-secret`.
3. `templates/globaldatasource-prometheus.yaml`,
   `globaldatasource-mesh-prometheus.yaml`, `globaldatasource-tempo.yaml` -
   three `PersesGlobalDatasource`s, cluster-scoped, each with
   `instanceSelector.matchLabels: {platform.opendatahub.io/part-of: monitoring}`
   (`data-science-perses`'s own live label). Datasource plugin shape copies
   RHOAI's own working `PersesDatasource` examples exactly -
   `plugin.spec.proxy: {kind: HTTPProxy, spec: {url, secret?}}`:
   - `prometheus`: `client.tls.caCert` reuses RHOAI's own
     `prometheus-web-tls-ca` ConfigMap (`redhat-ods-monitoring`, same
     thanos-querier endpoint); `proxy.spec.secret:
     zuno-perses-prometheus-reader-token`. `config.default: false` - do
     not contest RHOAI's own `cluster-prometheus-datasource`'s `default: true`.
   - `mesh-prometheus` / `tempo`: no auth, `proxy.spec.url` only.
4. `templates/uiplugin-dashboards.yaml` - one `UIPlugin`, `spec.type:
   Dashboards`. Kept deployed despite being confirmed non-functional on
   this cluster (harmless, forward-compatible - see Status updates).
5. `templates/dashboard-mesh-gateway.yaml` and
   `templates/dashboard-trustyai.yaml` - `metadata.name:
   zuno-mesh-gateway`/`zuno-trustyai`, `metadata.namespace:
   redhat-ods-monitoring` (ADR-0553 - not `zuno-mesh`/`zuno-ai-run`, the
   original ADR-0551 mapping). `instanceSelector` targets
   `data-science-perses`. Same per-panel translation otherwise. The
   `zuno-` name prefix avoids any collision with RHOAI's own eight
   dashboards now sharing this namespace (verified live: no overlap).
6. `gitops/apps/perses/application-d1.yaml` - unchanged shape (single
   Application, no `-d0`).
7. Run `platform/security/check_workload_hardening.py` against the new
   chart before considering this WP done.

## What NOT to touch

- No existing `gitops/charts/grafana/` file changes - this is additive only.
- No RHOAI-owned resource in `redhat-ods-monitoring` is modified, deleted,
  renamed, or depended upon beyond reading `data-science-perses`'s label
  and `prometheus-web-tls-ca`'s contents - see ADR-0552/ADR-0553's
  Operational considerations for the exact boundary. This WP adds more
  `PersesDashboard`/datasource objects into that namespace; it does not
  touch anything RHOAI already put there.
- No new Route or authentication - access is via RHOAI's existing
  `rhods-dashboard` "Monitor & observe" tab and `data-science-perses-route`,
  both unmodified.

## Tests / verification checklist

1. `oc get persesglobaldatasource,persesdashboard,uiplugin -A` (mine: 3
   global datasources, `zuno-mesh-gateway` and `zuno-trustyai` in
   `redhat-ods-monitoring`, `dashboards` UIPlugin) show `Ready`/`Available`
   conditions - **and** RHOAI's own eight `data-science-perses` dashboards
   in the same namespace are unaffected (still `Available: true`, unchanged
   resource count, no name collision).
2. `oc get application zuno-perses-d1 -n openshift-gitops` is
   `Synced`/`Healthy`.
3. Grafana untouched: the existing `Grafana` CR, all 3 `GrafanaDatasource`s
   and all 10 `GrafanaDashboard`s are still `Running`/synchronized with no
   diff introduced by this change.
4. `platform/security/check_workload_hardening.py` passes on
   `gitops/charts/perses/`.

## Live verification

Live-confirmed via the Perses REST API through RHOAI's
`data-science-perses-route` (`GET /api/v1/projects/redhat-ods-monitoring/dashboards`
returns both dashboards' full panel/query content) and via each
`PersesGlobalDatasource`'s own `Available: true` status (the `prometheus`
datasource's Bearer auth against thanos-querier genuinely works, not
assumed). Browser confirmation was also done, but disproved rather than
confirmed the intended visual path: `rhods-dashboard`'s "Observability
dashboard" only renders a fixed set of six RHOAI-specific tabs, not these
two - see Status updates and ADR-0553's dated correction note. No visual
rendering path exists for these dashboards on this cluster; the data layer
is this WP's actual, accepted completion gate.

## Status updates (then re-run check_docs.py)

- **2026-09-07, attempt 1, rolled back**: applied `zuno-perses-d1` with an
  independent `Perses` server instance per ADR-0551's original decision 2.
  Live-broke 7 of RHOAI's 8 `data-science-perses` dashboards for ~14 minutes
  (`instanceSelector`-less RHOAI resources resolved against the new,
  backend-less instance instead of their own). Fully rolled back: deleted
  the `zuno-perses-d1` Application and every child resource, then bounced
  `perses-operator` to clear its reconcile backoff. Confirmed recovered:
  7/7 affected RHOAI dashboards back to `Available: true` (the 8th,
  `data-science-tempo-traces`, has an unrelated pre-existing `$ref` bug
  predating this change). Zero Grafana impact throughout. ADR-0552 authored
  same day.
- **2026-09-07, attempt 2, applied, namespace-scoped
  (`zuno-mesh`/`zuno-ai-run`)**: `zuno-perses-d1` v2 (ADR-0552's design)
  applied successfully - one contained schema error found and fixed live
  (`plugin.spec.format` rejected on `TimeSeriesChart`/`Table` panels,
  accepted on `StatChart`). All 3 `PersesGlobalDatasource` and both
  `PersesDashboard`s reached `Available: true`, RHOAI unaffected. Browser
  access then found to have no working path: OpenShift console's
  `/monitoring/dashboards` (`LegacyDashboardsPage`) consumes no
  `console.dashboards/datasource` extension - confirmed by inspecting
  `monitoring-plugin`'s live manifest; `data-science-perses-route` serves
  Perses's own "forgot to generate the react app" placeholder - confirmed
  no frontend asset directory exists anywhere on the `data-science-perses-0`
  pod's filesystem (Red Hat's `perses-rhel9` image ships server-only).
  `rhods-dashboard`'s "Monitor & observe" tab does render real data but
  only from the `redhat-ods-monitoring` project (confirmed live by the
  user's browser, and traced to `rhods-dashboard`'s `core-bff` having no
  `perses.dev` RBAC at all - it calls Perses's REST API directly against
  that fixed project). ADR-0553 authored same day: collocate instead of
  split.
- **2026-09-07, attempt 3, applied - collocating in
  `redhat-ods-monitoring`**: `zuno-mesh-gateway`/`zuno-trustyai` created in
  `redhat-ods-monitoring`, both `Available: true`; old
  `zuno-mesh`/`zuno-ai-run` resources correctly pruned by ArgoCD; RHOAI's
  eight dashboards unaffected, no name collision.
- **2026-09-07, ADR-0553's hypothesis refuted, browser-confirmed**: logged
  into `rhods-dashboard`, opened "Observe & monitor" > "Observability
  dashboard" - it renders a **fixed set of six tabs** (Cluster, Models, LLM
  Traffic, LLM Utilization, Usage, LLM Performance), one per RHOAI's own
  `dashboard-N-*` resource, each also carrying a product-specific label
  (`platform.opendatahub.io/part-of: dashboard`/`kserve`) this repo's
  dashboards do not have. `zuno-mesh-gateway`/`zuno-trustyai` do not appear
  as tabs despite sharing the project - collocation bought no visibility.
  Confirmed with the user: keep the collocated placement anyway (avoid a
  fourth relocation); see ADR-0553's own dated correction note.
- **Closing state, confirmed with the user**: no visual rendering path
  exists for this repo's Perses dashboards anywhere on this cluster today
  (OpenShift console: no extension consumer; direct Route: no bundled
  frontend in Red Hat's image; `rhods-dashboard`: fixed tab list that
  doesn't include ours). Completion rests on the data layer, fully
  live-verified: both dashboards `Available: true`, correct panel/query
  content (confirmed via the Perses REST API), `prometheus` datasource
  Bearer auth against thanos-querier working, zero impact on Grafana or any
  RHOAI-owned resource throughout three redesign attempts in one day.
  `State` -> `Done` on that basis.
- `docs/roadmap/implementation-roadmap.md`'s Phase 41 tracker row for
  WP-138 updated to match.

## Out of scope / deferred

- The remaining eight Grafana dashboards - WP-139, once this WP's pattern is
  live-verified.
- Any Grafana deprecation - not decided by ADR-0551/ADR-0552/ADR-0553.
- Making the `UIPlugin` actually surface in the OpenShift console nav -
  blocked on an OCP/COO version pairing this repo does not control, not a
  repo-side task.

## Completion criteria

WP-138 is done when both pilot dashboards are `Available: true` with
correct, live-verified panel/query content (confirmed via the Perses REST
API, since no visual rendering path exists for them on this cluster - see
Status updates), both referencing the shared `PersesGlobalDatasource`s,
with zero changes to any existing Grafana or RHOAI-owned resource. Met
2026-09-07.
