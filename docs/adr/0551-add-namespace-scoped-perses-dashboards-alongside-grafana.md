# ADR-0551: Add namespace-scoped Perses dashboards alongside the existing Grafana stack

- **Status:** Accepted
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

## Related ADRs

- [ADR-0522](0522-enable-openshift-ai-monitoring-stack-side-by-side.md) - the
  ADR that named this option and deferred it; this decision fulfills it by
  choosing a COO-based Perses distinct from RHOAI's own, which stays
  untouched.
- [ADR-0413](0413-consolidate-grafana-dashboards-into-six-platform-views.md) -
  the Grafana dashboard set this ADR duplicates, unmodified.
- [ADR-0329](0329-consolidate-agent-workloads-into-the-shared-zuno-ai-run-namespace.md) -
  the namespace consolidation the mapping table above is built on.
- [ADR-0331](0331-revert-openshift-ai-to-the-default-applications-namespace.md) -
  background on `redhat-ods-monitoring` and RHOAI's own Perses, which this
  decision does not touch.
