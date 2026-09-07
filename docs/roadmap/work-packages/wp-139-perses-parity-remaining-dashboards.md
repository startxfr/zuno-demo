# WP-139: Perses parity for the remaining eight dashboards

- **State:** Not started
- **ADRs:** ADR-0551, ADR-0552
- **Depends on:** WP-138
- **Related:** none
- **Target:** v0.5
- **Estimated files touched:** 8 new `PersesDashboard` files under
  `gitops/charts/perses/templates/`; 0 existing Grafana files modified.

> Execute this brief as a standalone task from the repository root. Do not
> start before WP-138's pilot dashboards (`mesh-gateway`, `trustyai`) are
> live-verified - this WP reuses that pattern unchanged.

## Goal

Translate the remaining eight `GrafanaDashboard`s into namespace-scoped
`PersesDashboard`s, per ADR-0551's mapping table, targeting
`data-science-perses` (ADR-0552) via WP-138's three `PersesGlobalDatasource`s
and the `UIPlugin`, without modification to any of them. After this WP, all
ten Grafana dashboards have a live-verified Perses equivalent; Grafana
itself remains untouched and authoritative.

## Why this wasn't done in WP-138

WP-138 deliberately scoped itself to two pilots to validate the
server/datasource/scoping/console chain before committing to translating all
ten opaque Grafana JSON models - each is a real per-panel translation, not a
copy-paste, so bounding the initial risk mattered more than delivering full
parity in one pass.

## Repo changes

Add one `gitops/charts/perses/templates/dashboard-<name>.yaml` per row
below, translating panels from the corresponding
`gitops/charts/grafana/templates/dashboard-<name>.yaml` the same way WP-138
did for its two pilots (PromQL expressions and datasource UID references
carry over; panel/layout structure must be re-expressed in Perses's typed
schema):

| Dashboard (uid) | `metadata.namespace` | Note |
|---|---|---|
| `zuno-overview` | `zuno-monitoring` | Platform-scoped, no single owning namespace |
| `zuno-infra-data` | `zuno-monitoring` | Platform-scoped, cluster-wide |
| `zuno-usage-cost` | `zuno-monitoring` | Platform-scoped, cross-agent/provider |
| `zuno-run-trace` | `zuno-monitoring` | Platform-scoped, cross-service trace drill-down |
| `zuno-gitops` | `zuno-monitoring` | Platform-scoped; `openshift-gitops` is a system namespace |
| `zuno-ai-models` | `zuno-ai-run` | ai-gateway + vLLM/KServe predictors |
| `zuno-agents-tools-rag` | `zuno-ai-run` | agent-runtime, mcp-gateway, rag-service |
| `zuno-data` | `zuno-data` | Exception: the Redis panel actually observes `zuno-auth` - document this in the CR, do not silently drop or relocate it |

All eight reference the existing `PersesGlobalDatasource`s from WP-138 - no
new datasource resources.

## What NOT to touch

- No existing `gitops/charts/grafana/` file changes.
- No changes to WP-138's `Perses`/`PersesGlobalDatasource`/`UIPlugin`
  resources beyond what's strictly needed to add the new
  `PersesDashboard`s.

## Tests / verification checklist

1. `oc get persesdashboard -A` shows all 10 dashboards (2 from WP-138 + 8
   from this WP) `Ready` across their respective namespaces.
2. `platform/security/check_workload_hardening.py` passes on the updated
   chart.
3. Grafana untouched: same check as WP-138.

## Live verification

Same method as WP-138: real browser/console session confirming each of the
eight dashboards renders live data through the console's `UIPlugin`, with a
spot-check against its Grafana equivalent for the same time range.

## Status updates (then re-run check_docs.py)

- After live verification: this WP's `State` -> `Done`.
- `docs/roadmap/implementation-roadmap.md`'s Phase 41 tracker row for
  WP-139 updated to match.
- ADR-0551 gains a dated confirmation note that all ten dashboards reached
  parity, without changing its `Accepted`/`Implemented` status unless the
  ADR's own acceptance criteria require it.

## Out of scope / deferred

- Any Grafana deprecation - not decided by ADR-0551.
- Any further Perses dashboard beyond the ten that exist in Grafana today.

## Completion criteria

WP-139 is done when all eight remaining dashboards render correct, live data
through the OpenShift console's `UIPlugin`, each in the namespace ADR-0551's
mapping table specifies, with zero changes to any existing Grafana resource.
