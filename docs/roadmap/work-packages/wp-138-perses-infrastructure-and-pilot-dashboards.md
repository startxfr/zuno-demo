# WP-138: Perses datasources and pilot dashboards (mesh-gateway, trustyai)

- **State:** Not started (repo-side attempt 1 applied and rolled back
  2026-09-07 - see Status updates)
- **ADRs:** ADR-0551, ADR-0552
- **Depends on:** none
- **Related:** WP-139 (translates the remaining eight dashboards once this
  pattern is live-verified); WP-080 (owns `data-science-perses`, the Perses
  instance this WP now reuses read-only - see ADR-0552)
- **Target:** v0.5
- **Estimated files touched:** ~9 files under `gitops/charts/perses/` and
  `gitops/apps/perses/`; 3 new objects (ServiceAccount, Secret,
  ClusterRoleBinding) in `redhat-ods-monitoring`; 0 existing Grafana or
  RHOAI files/objects modified.

> Execute this brief as a standalone task from the repository root.

## Goal

Duplicate two of `zuno-monitoring`'s ten Grafana dashboards - `mesh-gateway`
and `trustyai` - as namespace-scoped `PersesDashboard`s on **RHOAI's
existing `data-science-perses` instance** (ADR-0552), backed by three shared
`PersesGlobalDatasource`s, surfaced in the OpenShift console via a COO
`UIPlugin`. This proves the whole chain (datasource auth against a shared
instance, cross-namespace scoping, console rendering, panel translation)
before WP-139 scales it to the remaining eight dashboards. Grafana is not
modified; no RHOAI-owned resource is modified or deleted.

## Why this work is required

ADR-0551 decided to duplicate Grafana's dashboards onto Perses, physically
split by application namespace. ADR-0552 changed how: attempt 1 ran an
independent second `Perses` server instance and broke RHOAI's own dashboards
live (see Status updates) - `instanceSelector`-less resources (exactly how
every RHOAI Perses resource is configured) match *any* Perses instance on
the cluster, a standard Kubernetes `LabelSelector` behavior, not a bug, and
not documented anywhere as a supported multi-instance configuration. Attempt
2 (this brief) reuses `data-science-perses` instead - never runs a second
instance - which structurally cannot reproduce that failure mode.

## Repo changes

1. **`gitops/charts/perses/`** - no `templates/perses.yaml` this time (no
   server CR). Chart stays a single `-d1`-only Application (no operator
   Subscription - COO is already subscribed via
   `gitops/apps/mesh-monitoring/application-d0.yaml`).
2. `templates/serviceaccount-prometheus-reader.yaml` - a **new**
   ServiceAccount (`zuno-perses-prometheus-reader`) + long-lived token
   Secret + ClusterRoleBinding to `cluster-monitoring-view`, all in
   **`redhat-ods-monitoring`** (not `zuno-monitoring` - this is where
   RHOAI's own `PersesDatasource`s resolve their `proxy.spec.secret`
   references from, inferred from their live examples, confirmed at this
   WP's live-verification step). Same shape as
   `gitops/charts/grafana/templates/serviceaccount-prometheus-reader.yaml`,
   different namespace and name (avoid any collision with RHOAI's own
   `cluster-prometheus-datasource-secret`).
3. `templates/globaldatasource-prometheus.yaml`,
   `globaldatasource-mesh-prometheus.yaml`, `globaldatasource-tempo.yaml` -
   three `PersesGlobalDatasource`s, cluster-scoped, each with
   `instanceSelector.matchLabels: {platform.opendatahub.io/part-of: monitoring}`
   (`data-science-perses`'s own live label - verify it hasn't changed before
   applying). Datasource plugin shape copies RHOAI's own working
   `PersesDatasource` examples exactly - `plugin.spec.proxy: {kind:
   HTTPProxy, spec: {url, secret?}}`, never `directUrl` (attempt 1's
   unverified guess):
   - `prometheus`: `client.tls.caCert` reuses RHOAI's own
     `prometheus-web-tls-ca` ConfigMap (`redhat-ods-monitoring`, same
     thanos-querier endpoint, no need to duplicate it);
     `proxy.spec.secret: zuno-perses-prometheus-reader-token` (this WP's own
     Secret from step 2). `config.default: false` - do not contest RHOAI's
     own `cluster-prometheus-datasource`'s `default: true`.
   - `mesh-prometheus` / `tempo`: no auth, `proxy.spec.url` only - same
     shape as RHOAI's own no-auth `data-science-prometheus-datasource`.
4. `templates/uiplugin-dashboards.yaml` - one `UIPlugin`, `spec.type:
   Dashboards` (unaffected by the ADR-0552 pivot - it also now surfaces
   RHOAI's own pre-existing dashboards in the console, accepted as a
   harmless side effect).
5. `templates/dashboard-mesh-gateway.yaml` (`metadata.namespace: zuno-mesh`)
   and `templates/dashboard-trustyai.yaml` (`metadata.namespace:
   zuno-ai-run`) - same per-panel translation as before, only
   `instanceSelector` changes to match `data-science-perses`.
6. `gitops/apps/perses/application-d1.yaml` - unchanged shape (single
   Application, no `-d0`).
7. Run `platform/security/check_workload_hardening.py` against the new
   chart before considering this WP done.

## What NOT to touch

- No existing `gitops/charts/grafana/` file changes - this is additive only.
- No RHOAI-owned resource in `redhat-ods-monitoring` is modified, deleted,
  or depended upon beyond reading `data-science-perses`'s label and
  `prometheus-web-tls-ca`'s contents - see ADR-0552's Operational
  considerations for the exact boundary.
- No new Route created or authentication added for direct Perses access -
  access, once the `UIPlugin`'s console path proved to have no consumer on
  this cluster (see Status updates), reuses WP-080's existing
  `data-science-perses-route` unmodified. This WP builds no new access
  surface of its own.

## Tests / verification checklist

1. `oc get persesglobaldatasource,persesdashboard,uiplugin -A` (mine: 3
   global datasources, `mesh-gateway` in `zuno-mesh`, `trustyai` in
   `zuno-ai-run`, `dashboards` UIPlugin) show `Ready`/`Available` conditions
   - **and** RHOAI's own `data-science-perses` resources are unaffected
   (still `Available: true`, unchanged resource count).
2. `oc get application zuno-perses-d1 -n openshift-gitops` is
   `Synced`/`Healthy`.
3. Grafana untouched: the existing `Grafana` CR, all 3 `GrafanaDatasource`s
   and all 10 `GrafanaDashboard`s are still `Running`/synchronized with no
   diff introduced by this change.
4. `platform/security/check_workload_hardening.py` passes on
   `gitops/charts/perses/`.

## Live verification

Confirmed via the Perses REST API through RHOAI's existing
`data-science-perses-route` (`redhat-ods-monitoring`, WP-080's own Route -
no new Route needed): `GET /api/v1/projects` lists both `zuno-mesh` and
`zuno-ai-run` projects, and `GET /api/v1/projects/<ns>/dashboards` returns
each dashboard's full panel content. The `prometheus` datasource's Bearer
auth against thanos-querier works (`PersesGlobalDatasource/prometheus` is
`Available: true`, live-confirmed, not assumed). Browser confirmation of
actual rendered panel data (not just the REST payload) still pending -
visit:

- `https://data-science-perses-route-redhat-ods-monitoring.<appsDomain>/projects/zuno-mesh/dashboards/mesh-gateway`
- `https://data-science-perses-route-redhat-ods-monitoring.<appsDomain>/projects/zuno-ai-run/dashboards/trustyai`

No console-nav access: see the dated finding below - the `UIPlugin` this WP
deploys has no OpenShift-console consumer on this cluster's exact version
combination, discovered live, not assumed.

## Status updates (then re-run check_docs.py)

- **2026-09-07, attempt 1, rolled back**: applied `zuno-perses-d1` with an
  independent `Perses` server instance per ADR-0551's original decision 2.
  Live-broke 7 of RHOAI's 8 `data-science-perses` dashboards for ~14 minutes
  (`instanceSelector`-less RHOAI resources resolved against the new,
  backend-less instance instead of their own - standard Kubernetes
  `LabelSelector` semantics, not a bug). Fully rolled back: deleted the
  `zuno-perses-d1` Application and every child resource (Perses CR, 3
  `PersesGlobalDatasource`, 2 `PersesDashboard`, the `UIPlugin`, the
  ServiceAccount/ClusterRoleBinding), then bounced `perses-operator` to
  clear its reconcile backoff. Confirmed recovered: 7/7 affected RHOAI
  dashboards back to `Available: true` (the 8th, `data-science-tempo-traces`,
  has an unrelated pre-existing `$ref` bug predating this change). Zero
  Grafana impact throughout. ADR-0552 authored same day, superseding
  ADR-0551's server-topology decision.
- **2026-09-07, attempt 2, applied successfully**: `zuno-perses-d1` v2
  (ADR-0552's design) applied. Live-caught one contained schema error - the
  Perses server rejected `plugin.spec.format` on `TimeSeriesChart`/`Table`
  panels ("field not allowed"; `StatChart` panels accept it, confirmed
  live) - fixed and reapplied via ArgoCD selfHeal, zero impact on anyone
  else. Final state: all 3 `PersesGlobalDatasource` and both
  `PersesDashboard`s `Available: true`, RHOAI's 7/8 relevant dashboards
  unchanged throughout, `zuno-perses-d1` `Synced`/`Healthy`.
- **2026-09-07, dated finding - the `UIPlugin` has no console consumer
  here**: the `console-dashboards-plugin` `ConsolePlugin` loads correctly
  (HTTP 200 from the console pod, `ClusterOperator/console` reports "All is
  well", enabled in `console.operator.openshift.io/cluster`'s
  `spec.plugins`) and publishes a `console.dashboards/datasource` extension
  - but the actual `/monitoring/dashboards` page on this cluster
  (`monitoring-plugin` 1.0.0, OCP 4.22.8) is rendered by a component
  literally named `LegacyDashboardsPage`, whose own manifest declares no
  extension that consumes `console.dashboards/datasource` - confirmed by
  inspecting `monitoring-plugin`'s live `plugin-manifest.json` from inside
  the console pod. This is a genuine version-compatibility gap between COO
  1.5.2's `Dashboards` `UIPlugin` type and this OCP release's console, not a
  misconfiguration - there is no fix available in this repo for it today.
  Access is via RHOAI's existing `data-science-perses-route` instead (see
  Live verification above) - ADR-0551's decision 4 (UIPlugin) still stands
  as *deployed* (harmless, and forward-compatible if a future OCP/COO
  pairing wires the consumer), just not as the working access path today.
- After browser confirmation of the two pilot dashboards' rendered panel
  data via the Route above: this WP's `State` -> `Done`.
- `docs/roadmap/implementation-roadmap.md`'s Phase 41 tracker row for
  WP-138 updated to match.

## Out of scope / deferred

- The remaining eight Grafana dashboards - WP-139, once this WP's pattern is
  live-verified.
- Any Grafana deprecation - not decided by ADR-0551/ADR-0552.
- Making the `UIPlugin` actually surface in the console nav - blocked on an
  OCP/COO version pairing this repo does not control (see the dated finding
  above), not a repo-side task.

## Completion criteria

WP-138 is done when both pilot `PersesDashboard`s render correct, live data
- confirmed via RHOAI's existing `data-science-perses-route`, since the
`UIPlugin` console path has no consumer on this cluster today - each
scoped to its own application namespace, both referencing the shared
`PersesGlobalDatasource`s, with zero changes to any existing Grafana or
RHOAI-owned resource.
