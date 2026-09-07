# WP-139: Perses parity for the remaining eight dashboards

- **State:** Not started
- **ADRs:** ADR-0551, ADR-0552, ADR-0553
- **Depends on:** WP-138
- **Related:** none
- **Target:** v0.5
- **Estimated files touched:** 8 new `PersesDashboard` files under
  `gitops/charts/perses/templates/`; 0 existing Grafana files modified.

> Execute this brief as a standalone task from the repository root. Do not
> start before WP-138's pilot dashboards (`zuno-mesh-gateway`,
> `zuno-trustyai`) are live-verified rendering in `rhods-dashboard`'s
> "Monitor & observe" tab - this WP reuses that pattern unchanged.

## Goal

Translate the remaining eight `GrafanaDashboard`s into `PersesDashboard`s,
all in **`redhat-ods-monitoring`** (ADR-0553 - not split per application
namespace, ADR-0551's original mapping), targeting `data-science-perses`
(ADR-0552) via WP-138's three `PersesGlobalDatasource`s, without
modification to any of them. After this WP, all ten Grafana dashboards have
a live-verified Perses equivalent, viewable in `rhods-dashboard`'s "Monitor
& observe" tab; Grafana itself remains untouched and authoritative.

## Why this wasn't done in WP-138

WP-138 deliberately scoped itself to two pilots to validate the
datasource/collocation/rendering chain before committing to translating all
ten opaque Grafana JSON models - each is a real per-panel translation, not a
copy-paste, so bounding the initial risk mattered more than delivering full
parity in one pass. WP-138 also had to revise its target namespace twice
live (see its own Status updates) before landing on `redhat-ods-monitoring`
- this brief starts from that already-settled design, not the original
per-namespace mapping.

## Repo changes

Add one `gitops/charts/perses/templates/dashboard-<name>.yaml` per row
below, translating panels from the corresponding
`gitops/charts/grafana/templates/dashboard-<name>.yaml` the same way WP-138
did for its two pilots (PromQL expressions and datasource references carry
over; panel/layout structure must be re-expressed in Perses's typed schema,
and `plugin.spec.format` must be omitted on `TimeSeriesChart`/`Table`
panels - WP-138's live-caught schema error). All eight get a `zuno-` name
prefix and `metadata.namespace: redhat-ods-monitoring`:

| Dashboard (Grafana uid) | `PersesDashboard` name | Note |
|---|---|---|
| `zuno-overview` | `zuno-overview` | Landing page, no single owning application namespace |
| `zuno-infra-data` | `zuno-infra-data` | Cluster-wide node/pod health |
| `zuno-usage-cost` | `zuno-usage-cost` | Cross-agent/provider cost aggregation |
| `zuno-run-trace` | `zuno-run-trace` | Cross-service trace drill-down |
| `zuno-gitops` | `zuno-gitops` | ArgoCD sync/health |
| `zuno-ai-models` | `zuno-ai-models` | ai-gateway + vLLM/KServe predictors |
| `zuno-agents-tools-rag` | `zuno-agents-tools-rag` | agent-runtime, mcp-gateway, rag-service |
| `zuno-data` | `zuno-data` | Exception: the Redis panel actually observes `zuno-auth` - document this in the CR, do not silently drop or relocate it |

Before adding each, `oc get persesdashboard -n redhat-ods-monitoring` to
confirm no name collision with RHOAI's own eight dashboards or WP-138's two
- none are expected (RHOAI's own use a `dashboard-N-*` naming convention,
this repo's all start with `zuno-`), but verify rather than assume. All
eight reference the existing `PersesGlobalDatasource`s from WP-138 - no new
datasource resources.

## What NOT to touch

- No existing `gitops/charts/grafana/` file changes.
- No changes to WP-138's `PersesGlobalDatasource`/`UIPlugin` resources
  beyond what's strictly needed to add the new `PersesDashboard`s.
- No RHOAI-owned resource in `redhat-ods-monitoring` is modified, deleted,
  or renamed - same boundary as WP-138 (see ADR-0552/ADR-0553's
  Operational considerations).

## Tests / verification checklist

1. `oc get persesdashboard -n redhat-ods-monitoring` shows all 10 of this
   repo's dashboards (2 from WP-138 + 8 from this WP) `Available: true`,
   alongside RHOAI's own eight, unchanged and unaffected.
2. `platform/security/check_workload_hardening.py` passes on the updated
   chart.
3. Grafana untouched: same check as WP-138.

## Live verification

Same method as WP-138: log into `rhods-dashboard`, open "Monitor & observe",
confirm each of the eight dashboards appears and renders live data, with a
spot-check against its Grafana equivalent for the same time range.

## Status updates (then re-run check_docs.py)

- After live verification: this WP's `State` -> `Done`.
- `docs/roadmap/implementation-roadmap.md`'s Phase 41 tracker row for
  WP-139 updated to match.
- ADR-0551 gains a dated confirmation note that all ten dashboards reached
  parity, without changing its `Accepted`/`Superseded in part` status
  unless the ADR's own acceptance criteria require it.

## Out of scope / deferred

- Any Grafana deprecation - not decided by ADR-0551/ADR-0552/ADR-0553.
- Any further Perses dashboard beyond the ten that exist in Grafana today.
- Making the `UIPlugin` surface in the OpenShift console nav - platform gap,
  not a repo-side task (see WP-138).

## Completion criteria

WP-139 is done when all eight remaining dashboards render correct, live data
in `rhods-dashboard`'s "Monitor & observe" tab, alongside WP-138's two
pilots and RHOAI's own, with zero changes to any existing Grafana or
RHOAI-owned resource.
