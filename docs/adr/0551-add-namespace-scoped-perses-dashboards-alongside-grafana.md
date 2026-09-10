# ADR-0551: Add namespace-scoped Perses dashboards alongside the existing Grafana stack

- **Status:** Superseded in part by ADR-0552 (decisions 2 and 3 - server
  topology and datasource strategy) and by ADR-0553 (decisions 1 and 6 -
  physical namespace split and namespace mapping). Decisions 4 (`UIPlugin`
  console integration - deployed, confirmed non-functional on this cluster,
  see the second dated correction note) and 5 (phased WP-138/WP-139
  rollout) remain this record's own decisions, unchanged.
- **Target:** v0.5
- **Date:** 2026-09-07
- **Decision owners:** Zuno Demo architecture team

## Context

`gitops/charts/grafana` runs one `Grafana` instance, three `GrafanaDatasource`s
(`prometheus` against `thanos-querier`, `mesh-prometheus` against the mesh's
own Prometheus, `tempo`) and ten `GrafanaDashboard`s, all in `zuno-monitoring`
(`grafana.integreatly.org/v1beta1`, Grafana Operator v5). The dashboard set is
deliberately consolidated ([ADR-0413](0413-consolidate-grafana-dashboards-into-six-platform-views.md)):
a handful of wide dashboards filtered by a `namespace` template variable,
rather than one dashboard per application namespace.

[ADR-0522](0522-enable-openshift-ai-monitoring-stack-side-by-side.md)'s
Migration/evolution section explicitly left one call unmade: *"A later ADR
must make that call explicitly, choosing among ... migrating
`zuno-monitoring`'s Grafana dashboards onto RHOAI's Perses ... Until such an
ADR lands, both stacks are independently owned and independently operated."*
This is that later ADR - but it does not choose the option ADR-0522 named.
RHOAI's own Perses (`data-science-perses`, `redhat-ods-monitoring`, exposed by
WP-080's `data-science-perses-route`) is provisioned and owned by the RHOAI
operator itself, observes RHOAI-managed workloads only, and is left exactly
as ADR-0522 configured it - untouched, unmerged, out of scope here.

Separately, the Cluster Observability Operator (COO) v1.5.2 is already
installed cluster-wide (subscribed via
`gitops/apps/mesh-monitoring/application-d0.yaml`, confirmed live in
`openshift-cluster-observability-operator`) and registers its own Perses
CRDs - `perses.dev/v1alpha2`'s `Perses`, `PersesDashboard`, `PersesDatasource`
and `PersesGlobalDatasource` - plus a `UIPlugin` CRD for console integration.
Live-checked 2026-09-07: the CRDs exist, zero instances of any of them are
deployed anywhere on the cluster. This is a greenfield addition, not a
migration of RHOAI's Perses.

## Decision

Stand up a second, independent Perses deployment - built on the
already-installed COO CRDs, not RHOAI's own Perses - that duplicates every
`zuno-monitoring` Grafana dashboard as a typed `PersesDashboard`, scoped by
application namespace, and surfaced natively in the OpenShift console.
Grafana is not modified, reduced, or deprecated by this decision.

1. **Scoping is a physical split, not a template filter.** Each
   `PersesDashboard` lives in the application namespace it actually observes,
   instead of one `zuno-monitoring`-only CR filtered by a `namespace`
   variable. A dashboard with no single owning application namespace (see
   the mapping table below) stays `platform`-scoped in `zuno-monitoring`.
2. **One `Perses` server instance**, in `zuno-monitoring`, mirroring the
   single `Grafana` instance today. Namespace scoping is achieved by where
   each `PersesDashboard`/`PersesDatasource` resource lives plus
   `instanceSelector` (label `dashboards: perses`), not by running one
   Perses server per namespace.
3. **Datasources are `PersesGlobalDatasource`s**, cluster-scoped, defined
   once for the same three backends Grafana already uses (`prometheus`
   against `thanos-querier`, `mesh-prometheus`, `tempo`), and referenced by
   every `PersesDashboard` regardless of which namespace it lives in. No
   per-namespace datasource duplication.
4. **Console integration via a COO `UIPlugin`** (`spec.type: Dashboards`),
   giving Perses a real navigation entry and embedded rendering inside the
   OpenShift console - not a bare Route, which is how Grafana is reached
   today (`grafana-route-zuno-monitoring...`, with no console presence at
   all: `oc get consolelink/consoleplugin -A` shows nothing for Grafana).
5. **Phased rollout.** WP-138 stands up the server, the three
   `PersesGlobalDatasource`s, the `UIPlugin`, and translates two pilot
   dashboards end to end (`mesh-gateway` and `trustyai`). WP-139 translates
   the remaining eight once WP-138's pattern is live-verified. Grafana's
   opaque `schemaVersion 39` JSON model has no 1:1 mapping onto Perses's
   typed `panels`/`layouts`/`queries` schema, so each dashboard is a real
   per-panel translation, not a copy-paste - phasing bounds that risk.
6. **Namespace mapping** ([ADR-0329](0329-consolidate-agent-workloads-into-the-shared-zuno-ai-run-namespace.md)
   already put most application workloads into a shared `zuno-ai-run`
   namespace, so three of the ten dashboards below converge on the same
   target - the split separates them from `zuno-monitoring`, not from each
   other):

   | Dashboard (uid) | Target namespace | Basis |
   |---|---|---|
   | `zuno-overview` | `zuno-monitoring` (platform) | Landing page, no single owning namespace |
   | `zuno-infra-data` | `zuno-monitoring` (platform) | Cluster-wide node/pod, filtered by `$namespace` |
   | `zuno-usage-cost` | `zuno-monitoring` (platform) | Cross-agent/cross-provider cost aggregation |
   | `zuno-run-trace` | `zuno-monitoring` (platform) | Per-run trace spanning multiple services, no single owner |
   | `zuno-gitops` | `zuno-monitoring` (platform) | `openshift-gitops` is a system namespace, not applicative |
   | `zuno-ai-models` | `zuno-ai-run` | ai-gateway and the vLLM/KServe predictors live there |
   | `zuno-agents-tools-rag` | `zuno-ai-run` | agent-runtime, mcp-gateway, rag-service (ADR-0329) |
   | `zuno-trustyai` | `zuno-ai-run` (WP-138 pilot) | `gitops/apps/trustyai-config/application-d1.yaml` |
   | `zuno-data` | `zuno-data` | Exception, documented: the Redis panel actually observes `zuno-auth` |
   | `zuno-mesh-gateway` | `zuno-mesh` (WP-138 pilot) | Already has its own dedicated `mesh-prometheus` datasource |

## Operational considerations

No new NetworkPolicy is expected for datasource access itself: `zuno-mesh`'s
`allowedFromNamespaces` already allows `zuno-monitoring` (Grafana's own
`mesh-prometheus` scrape uses the same path), and the new Perses server lives
in the same `zuno-monitoring` namespace. A NetworkPolicy gap is plausible on
the *operator* side instead: `zuno-monitoring`'s `allowedFromNamespaces`
explicitly allowlists `openshift-grafana-operator` today because the Grafana
Operator's controller calls back into its managed instance's admin API - the
COO/Perses-operator relationship is the same shape, so
`openshift-cluster-observability-operator` will likely need the same
allowance. This is confirmed or fixed during WP-138, not decided here.
`UIPlugin.spec.type: Dashboards` takes no further sub-configuration in COO
1.5.2 (verified via `oc explain`). New charts still need a
`platform/security/check_workload_hardening.py` pass, per standing
convention.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Security considerations, Acceptance criteria and
Review evidence.

## Migration / evolution

Grafana remains the source of truth for every dashboard until WP-139 reaches
parity; this ADR does not set a Grafana deprecation date or commit to ever
retiring it - the two stacks are additive, exactly as ADR-0522 kept
`zuno-monitoring` and RHOAI's monitoring independently owned. A future ADR
would be needed to change that.

## Dated correction note (2026-09-07)

Decision 2 ("one Perses server instance") was applied live via WP-138 and
immediately rolled back: `PersesDashboard`/`PersesDatasource`/
`PersesGlobalDatasource` resources with no `instanceSelector` set - which is
exactly how every one of RHOAI's own resources is configured - resolve
against **any** Perses instance on the cluster (a standard Kubernetes
`LabelSelector` with no fields matches everything), not just the intended
one. The moment this ADR's second, independent Perses instance appeared,
several of RHOAI's own dashboards (`redhat-ods-monitoring`) started
resolving against it instead of `data-science-perses`, breaking them for
~14 minutes until the instance was deleted. Confirmed against upstream
Perses/Red Hat documentation: running more than one Perses instance per
cluster is not a supported or even discussed configuration - see
[ADR-0552](0552-reuse-rhoais-perses-instance-instead-of-running-an-independent-one.md),
which replaces decisions 2 and 3 with reusing `data-science-perses`.

## Second dated correction note (2026-09-07)

Decision 4 (the `UIPlugin` console integration) was deployed successfully -
the `console-dashboards-plugin` `ConsolePlugin` loads (`HTTP 200` from the
console pod, `ClusterOperator/console` "All is well", enabled in
`console.operator.openshift.io/cluster`) and publishes a
`console.dashboards/datasource` extension - but live inspection of this
cluster's `monitoring-plugin` (1.0.0, OCP 4.22.8) found that the actual
`/monitoring/dashboards` page is rendered by a component named
`LegacyDashboardsPage`, which declares no extension consuming
`console.dashboards/datasource`. There is no OpenShift-console UI on this
exact version pairing that reads Perses dashboards at all - a genuine
version-compatibility gap between COO 1.5.2's `Dashboards` `UIPlugin` type
and this OCP release, discovered live, not something this repo can fix.
WP-138 accesses the dashboards via RHOAI's existing
`data-science-perses-route` (WP-080) instead - see WP-138's own dated
finding for the full detail. The `UIPlugin` remains deployed (harmless,
forward-compatible if a future OCP/COO pairing wires the consumer) but is
not, today, a working access path.

## Third dated correction note (2026-09-07)

Following the second note above, `data-science-perses-route` itself turned
out to be a dead end too - Red Hat's `perses-rhel9` image ships without its
bundled React frontend at all (confirmed live: no frontend asset directory
on the pod's filesystem; the Route serves Perses's own hardcoded "forgot to
generate the react app" placeholder). The dashboards render nowhere as a
standalone Perses UI on this cluster. The one working path found:
`rhods-dashboard`'s "Monitor & observe" tab (a RHOAI product surface, not
the OpenShift console) - but it only shows dashboards from the
`redhat-ods-monitoring` project, hardcoded, confirmed by inspecting
`rhods-dashboard`'s own RBAC (no `perses.dev` access at all - it calls
Perses's REST API directly against that fixed project name). Decisions 1
and 6 (the physical namespace split and its mapping table) are superseded
by [ADR-0553](0553-collocate-perses-dashboards-in-redhat-ods-monitoring-for-visibility.md),
which moves every dashboard into `redhat-ods-monitoring` to make this the
working access path, trading away per-application-namespace placement for
actual human-visible rendering.

## Fourth dated confirmation note (2026-09-10)

WP-139 applied the remaining eight dashboards to `demo333` and confirmed
all ten `PersesDashboard`s (WP-138's two pilots plus these eight) reached
`Available: true`, with panel/query content spot-checked against the
Perses REST API. Decision 4 (`UIPlugin`) and decision 5 (phased WP-138/
WP-139 rollout) are now both fully executed; this note does not change the
`Superseded in part` status above, which remains accurate for decisions
1/6 (ADR-0553) and 2/3 (ADR-0552).

## Related ADRs

- [ADR-0522](0522-enable-openshift-ai-monitoring-stack-side-by-side.md) - the
  ADR that named this option and deferred it; this decision fulfills it,
  though [ADR-0552](0552-reuse-rhoais-perses-instance-instead-of-running-an-independent-one.md)
  changed HOW - reusing RHOAI's Perses instance rather than running a second
  one.
- [ADR-0413](0413-consolidate-grafana-dashboards-into-six-platform-views.md) -
  the Grafana dashboard set this ADR duplicates, unmodified.
- [ADR-0329](0329-consolidate-agent-workloads-into-the-shared-zuno-ai-run-namespace.md) -
  the namespace consolidation the mapping table above is built on.
- [ADR-0331](0331-revert-openshift-ai-to-the-default-applications-namespace.md) -
  background on `redhat-ods-monitoring` and RHOAI's own Perses, which this
  decision does not touch.
