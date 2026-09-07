# ADR-0553: Collocate Perses dashboards in redhat-ods-monitoring for real visibility

- **Status:** Accepted
- **Target:** v0.5
- **Date:** 2026-09-07
- **Decision owners:** Zuno Demo architecture team
- **Supersedes ADR-0551** in part (decisions 1 "physical namespace split" and
  6 "namespace mapping table"). ADR-0551's decisions 4 (`UIPlugin`, still
  deployed, still non-functional on this cluster) and 5 (phased WP-138/
  WP-139 rollout) are unaffected. ADR-0552's decisions (reuse
  `data-science-perses`, datasource auth strategy) are unaffected and remain
  the foundation this ADR builds on.

## Context

WP-138's live verification, after ADR-0552 fixed the instance-collision
incident, found that **no visual rendering path for Perses dashboards
exists on this cluster for namespace-scoped dashboards**, discovered by
elimination:

1. The OpenShift console's `/monitoring/dashboards` page is rendered by
   `monitoring-plugin`'s `LegacyDashboardsPage` component, which consumes no
   `console.dashboards/datasource` extension - the `UIPlugin` this repo
   deploys (ADR-0551 decision 4) has no console consumer on this OCP 4.22.8
   release (see ADR-0551's second dated correction note).
2. RHOAI's own `data-science-perses-route` (WP-080) returns Perses's own
   hardcoded placeholder ("looks like you forget to generate the react app
   before generating the golang endpoint") - Red Hat's `perses-rhel9` image
   ships without its bundled React frontend, confirmed live (no frontend
   asset directory anywhere on the pod's filesystem). There is no standalone
   Perses UI to browse on this image at all.
3. **RHOAI's own ODH Dashboard app** (`rhods-dashboard`, a separate web
   application from the OpenShift console) has a working "Monitor & observe"
   tab that does render real Perses dashboard data - but live-confirmed
   (user, browser) it shows only RHOAI's own dashboards (`dashboard-0-
   cluster-admin` etc.), not this repo's `mesh-gateway`/`trustyai`. Traced
   to `rhods-dashboard`'s `core-bff` container: its `ClusterRole` grants no
   RBAC on `perses.dev` resources at all, so it must call Perses's own REST
   API directly against a fixed, RHOAI-known project name
   (`redhat-ods-monitoring`) rather than discovering dashboards dynamically
   across projects - not configurable from this repo's side.

No available upgrade path exists either: the cluster's OperatorHub catalog
offers only `cluster-observability-operator.v1.5.2` on both its `fast` and
`stable` channels - no newer version to try.

## Decision

Move every Perses dashboard this repo defines into the **`redhat-ods-monitoring`**
project - the one project RHOAI's "Monitor & observe" tab actually renders -
instead of splitting them across each dashboard's owning application
namespace (ADR-0551's original decision 1/6). This is the only currently
available way to make these dashboards visually visible to a human on this
cluster.

1. **`PersesDashboard.metadata.namespace: redhat-ods-monitoring`** for all
   ten dashboards (WP-138's two pilots, WP-139's remaining eight) -
   replacing ADR-0551's mapping table entirely. Namespace is immutable on an
   existing object; the two already-applied pilots
   (`gitops/charts/perses/templates/dashboard-mesh-gateway.yaml`,
   `dashboard-trustyai.yaml`) are deleted and recreated under this new
   namespace via ArgoCD's own prune-and-create on the next sync, not
   hand-migrated.
2. **Renamed with a `zuno-` prefix** (`zuno-mesh-gateway`, `zuno-trustyai`,
   and so on for WP-139's eight) to keep clear, collision-free ownership
   now that this repo's dashboards live alongside RHOAI's own
   (`dashboard-0-cluster-admin` etc.) in the same project - verified live,
   no name collision with any of RHOAI's four existing datasources or eight
   existing dashboards.
3. The three `PersesGlobalDatasource`s (ADR-0552) are unaffected - already
   cluster-scoped, already visible from any project including
   `redhat-ods-monitoring`.
4. What this explicitly gives up: per-namespace RBAC isolation for these
   dashboards (anyone who can read `redhat-ods-monitoring` can now read all
   ten, not just the ones for their own application namespace) and the
   original "dashboard lives next to the workload it observes" placement
   logic. What it buys: dashboards a human can actually open and see
   render, today, via `rhods-dashboard`'s "Monitor & observe" tab - the
   entire point of ADR-0551 in the first place.

## Operational considerations

Still additive-only: no RHOAI-owned `PersesDashboard`/`PersesDatasource`/
label/ConfigMap is modified, deleted, or renamed - this ADR only adds more
`PersesDashboard` objects into the same namespace RHOAI's own already live
in, exactly as ADR-0552 already established for the ServiceAccount/Secret.
The one operational difference: this repo's dashboards can no longer be
pruned/reasoned about per application namespace - `oc get persesdashboard -n
redhat-ods-monitoring` now shows both RHOAI's and this repo's, distinguished
only by the `zuno-` name prefix and (unlike RHOAI's) the
`zuno.io/managed-by: argocd` label already applied to every resource this
repo's chart renders.

`rhods-dashboard`'s "Monitor & observe" tab is a RHOAI product surface, not
literally "the OpenShift console" the user originally asked for - it is a
separate web application (own Route, own login) most commonly reached from
the OpenShift console's own application launcher. This ADR treats it as
close enough to satisfy the original request given the OpenShift console's
own path is confirmed non-functional on this cluster (see Context above);
if that distinction matters, say so and this decision should be revisited.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Security considerations, Acceptance criteria and
Review evidence.

## Dated correction note (2026-09-07)

This ADR's stated benefit did not materialize: live-verified in the
browser, `rhods-dashboard`'s "Observability dashboard" ("Monitor &
observe" > Dashboard) renders a **fixed, hardcoded set of six tabs**
(Cluster, Models, LLM Traffic, LLM Utilization, Usage, LLM Performance),
matching RHOAI's own `dashboard-N-*`-named resources one by one - not a
dynamic listing of every `PersesDashboard` in the `redhat-ods-monitoring`
project. `zuno-mesh-gateway`/`zuno-trustyai` do not appear as tabs despite
sharing the project; RHOAI's own dashboards additionally carry
product-specific labels (`platform.opendatahub.io/part-of: dashboard` /
`kserve`) this repo's do not and cannot match. Collocating in
`redhat-ods-monitoring` therefore bought no visibility benefit over the
original per-application-namespace split.

**Decision, confirmed with the user 2026-09-07**: keep the collocated
placement anyway, to avoid a third relocation churn cycle in one day. This
ADR's placement decision (dashboards in `redhat-ods-monitoring`) stands as
the final architecture, on record as **not delivering its original
justification** - a deliberate, accepted trade documented here rather than
silently left inconsistent with its own Context section. No further
dashboard-visibility work is planned; see WP-138's Status updates for the
closing state.

## Migration / evolution

If a future OCP/COO version wires `LegacyDashboardsPage` (or a successor) to
actually consume the `console.dashboards/datasource` extension, or ships a
Perses image with its bundled frontend, revisit whether namespace-scoped
placement (ADR-0551's original decision) becomes viable again without
losing visibility - not decided here.

## Related ADRs

- [ADR-0551](0551-add-namespace-scoped-perses-dashboards-alongside-grafana.md) -
  the record this ADR partially supersedes (decisions 1 and 6); its
  UIPlugin and phased-rollout decisions stand unchanged.
- [ADR-0552](0552-reuse-rhoais-perses-instance-instead-of-running-an-independent-one.md) -
  the datasource-reuse foundation this ADR builds on, unaffected.
- [ADR-0522](0522-enable-openshift-ai-monitoring-stack-side-by-side.md)/[WP-080](../roadmap/work-packages/wp-080-rhoai-monitoring-perses-route-dashboard.md) -
  owns `data-science-perses` and `rhods-dashboard`'s "Monitor & observe" tab,
  now the confirmed working access path.
