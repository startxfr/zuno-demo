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
- No Route or authentication decision for direct Perses access - the
  `UIPlugin` console path is the only access surface this WP builds.

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

Use this repo's established frontend/console verification method (real
browser session, not a synthetic check): confirm the OpenShift console shows
a Perses navigation entry from the `UIPlugin`, that both `mesh-gateway` and
`trustyai` dashboards render with live data, that the `prometheus`
datasource's Bearer auth against thanos-querier actually works (the one
genuinely unverified piece of this design), and that RHOAI's own dashboards
in the same console view are unaffected.

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
- After live verification of attempt 2 (this brief's design): this WP's
  `State` -> `Done`.
- `docs/roadmap/implementation-roadmap.md`'s Phase 41 tracker row for
  WP-138 updated to match.

## Out of scope / deferred

- The remaining eight Grafana dashboards - WP-139, once this WP's pattern is
  live-verified.
- Any Grafana deprecation or Route/auth changes for Perses - not decided by
  ADR-0551/ADR-0552.

## Completion criteria

WP-138 is done when both pilot `PersesDashboard`s render correct, live data
through the OpenShift console's `UIPlugin` via `data-science-perses`, each
scoped to its own application namespace, both referencing the shared
`PersesGlobalDatasource`s, with zero changes to any existing Grafana or
RHOAI-owned resource.
