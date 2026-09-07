# WP-138: Perses infrastructure and pilot dashboards (mesh-gateway, trustyai)

- **State:** Not started
- **ADRs:** ADR-0551
- **Depends on:** none
- **Related:** WP-139 (translates the remaining eight dashboards once this
  pattern is live-verified); WP-080 (RHOAI's own Perses instance in
  `redhat-ods-monitoring` - a distinct deployment, not touched here)
- **Target:** v0.5
- **Estimated files touched:** ~10 new files under `gitops/charts/perses/`
  and `gitops/apps/perses/`; 0 existing Grafana files modified.

> Execute this brief as a standalone task from the repository root.

## Goal

Stand up a second, independent Perses deployment (COO's `perses.dev/v1alpha2`
CRDs, already registered cluster-wide with zero instances) that duplicates
two of `zuno-monitoring`'s ten Grafana dashboards - `mesh-gateway` and
`trustyai` - as namespace-scoped `PersesDashboard`s, backed by shared
`PersesGlobalDatasource`s and surfaced in the OpenShift console via a COO
`UIPlugin`. This proves the whole chain (server, datasource sharing,
cross-namespace scoping, console rendering, panel translation) before WP-139
scales it to the remaining eight dashboards. Grafana is not modified.

## Why this work is required

ADR-0551 decided to duplicate Grafana's dashboards onto Perses, physically
split by application namespace, rather than leave the ADR-0522 "later ADR"
call unmade. Nothing exists yet: COO v1.5.2 is installed and its CRDs are
registered, but `oc get perses/persesdashboard/persesdatasource/uiplugin -A`
returns no resources anywhere on the cluster - this is greenfield work, not a
migration of an existing instance.

## Repo changes

1. **New chart `gitops/charts/perses/`** (`Chart.yaml`, `values.yaml`),
   mirroring `gitops/charts/connectivity-link-quota`'s shape: a single
   Application, no operator subscription of its own - COO is already
   subscribed via `gitops/apps/mesh-monitoring/application-d0.yaml`, so a
   `-d0` for Perses would re-subscribe the same operator and create an
   ArgoCD ownership conflict. Do not add one.
2. `templates/perses.yaml` - one `Perses` CR in `zuno-monitoring`, label
   `dashboards: perses` for `instanceSelector` matching (mirrors Grafana's
   own `dashboards: grafana` convention in `templates/grafana.yaml`).
3. `templates/globaldatasource-prometheus.yaml`,
   `globaldatasource-mesh-prometheus.yaml`, `globaldatasource-tempo.yaml` -
   three `PersesGlobalDatasource`s, cluster-scoped, reusing the exact URLs
   and UIDs of the three existing `GrafanaDatasource`s
   (`gitops/charts/grafana/templates/datasource-*.yaml`) so panel
   translation can reference the same backend semantics.
4. `templates/uiplugin-dashboards.yaml` - one `UIPlugin`,
   `spec.type: Dashboards` (no further sub-config needed per `oc explain
   uiplugin.spec` on this cluster's COO 1.5.2).
5. `templates/dashboard-mesh-gateway.yaml` (`metadata.namespace: zuno-mesh`)
   and `templates/dashboard-trustyai.yaml` (`metadata.namespace:
   zuno-ai-run`) - hand-translate each panel of
   `gitops/charts/grafana/templates/dashboard-mesh-gateway.yaml` and
   `dashboard-trustyai.yaml`'s opaque `spec.json` (schemaVersion 39) into
   Perses's typed `spec.config.panels`/`layouts`/`queries` schema. This is a
   real per-panel translation - Grafana's PromQL expressions and datasource
   UID references carry over, but the panel/layout structure does not.
6. `gitops/apps/perses/application-d1.yaml` - single ArgoCD Application
   (no `-d0`), destination namespace `zuno-monitoring` for the `Perses`
   CR/`UIPlugin`/`PersesGlobalDatasource`s; the two `PersesDashboard`s carry
   their own `metadata.namespace` (the `zuno` AppProject already allows
   `namespace: '*'` destinations).
7. Check whether `zuno-monitoring`'s NetworkPolicy
   (`gitops/charts/namespaces/values.yaml`'s `allowedFromNamespaces`) needs
   `openshift-cluster-observability-operator` added, mirroring the existing
   `openshift-grafana-operator` entry documented there for the same
   controller-callback reason. Add it only if live testing shows the Perses
   CR fails to reconcile without it - do not add speculatively.
8. Run `platform/security/check_workload_hardening.py` against the new
   chart before considering this WP done.

## What NOT to touch

- No existing `gitops/charts/grafana/` file changes - this is additive only.
- No changes to RHOAI's `redhat-ods-monitoring` Perses (WP-080) - distinct
  deployment, out of scope.
- No Route or authentication decision for direct Perses access - the
  `UIPlugin` console path is the only access surface this WP builds.

## Tests / verification checklist

1. `oc get perses,persesglobaldatasource,persesdashboard,uiplugin -n
   zuno-monitoring` (and `-n zuno-mesh` / `-n zuno-ai-run` for the two
   dashboards) show `Ready`/healthy conditions.
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
`trustyai` dashboards render with live data, and that the panel values match
their Grafana equivalents for the same time range (spot-check, not
pixel-for-pixel).

## Status updates (then re-run check_docs.py)

- After live verification: this WP's `State` -> `Done`, with the date and a
  one-line summary of what was confirmed (per this repo's WP convention).
- `docs/roadmap/implementation-roadmap.md`'s Phase 41 tracker row for
  WP-138 updated to match.
- If the NetworkPolicy gap in step 7 above was real and fixed, record it as
  a dated finding here, the same way Grafana's own operator-callback gap is
  documented in `gitops/charts/namespaces/values.yaml`.

## Out of scope / deferred

- The remaining eight Grafana dashboards - WP-139, once this WP's pattern is
  live-verified.
- Any Grafana deprecation or Route/auth changes for Perses - not decided by
  ADR-0551.

## Completion criteria

WP-138 is done when both pilot `PersesDashboard`s render correct, live data
through the OpenShift console's `UIPlugin`, each scoped to its own
application namespace, both referencing the shared `PersesGlobalDatasource`s,
with zero changes to any existing Grafana resource.
