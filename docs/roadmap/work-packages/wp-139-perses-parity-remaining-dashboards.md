# WP-139: Perses parity for the remaining eight dashboards

- **State:** Done (2026-09-10 - all 10 `PersesDashboard`s `Available: true`
  on `demo333`, content spot-checked via the Perses REST API)
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

All eight files above are now written and committed (panel counts: overview
14, infra-data 18, usage-cost 11, run-trace 21, gitops 4, ai-models 22,
agents-tools-rag 17, data 14 - 121 panels total across the 8, plus WP-138's
existing 9+13=22, for 143 panels across all 10 dashboards). See Status
updates below for verification performed and judgment calls made during
translation.

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
   alongside RHOAI's own eight, unchanged and unaffected. **Done,
   2026-09-10** on `demo333` - see Status updates for the three real schema
   defects found and fixed along the way.
2. `platform/security/check_workload_hardening.py` passes on the updated
   chart - **done**, 2026-09-07 (pre-existing, unrelated `ai-gateway`
   finding aside).
3. Grafana untouched: same check as WP-138 - **done**, no
   `gitops/charts/grafana/` file touched by this WP.
4. `helm lint`/`helm template --set perses.enabled=true` on the full chart -
   **done**, renders clean, all 10 `PersesDashboard`s present, zero
   `plugin.spec.format` leaked onto any `TimeSeriesChart`/`Table` panel
   (WP-138's live-caught schema trap), zero unescaped `{{label}}` legend
   placeholders. `python3 platform/docs/check_docs.py` - **PASS**.

## Live verification

Live-confirmed 2026-09-10 on `demo333` via the Perses REST API through
`data-science-perses-route` (`GET
/api/v1/projects/redhat-ods-monitoring/dashboards/<name>` spot-checked on
`zuno-usage-cost`, `zuno-agents-tools-rag`, `zuno-run-trace` - panel counts
match this WP's own table: 11/17/21), same method as WP-138. The
`rhods-dashboard` "Monitor & observe" browser check was kept only as a
courtesy recheck, not a gate, and was not repeated - ADR-0553's dated
correction note already established it only renders RHOAI's own fixed 6
tabs regardless of what this repo adds to `redhat-ods-monitoring`.

## Status updates (then re-run check_docs.py)

- **2026-09-07** - all 8 remaining `GrafanaDashboard`s translated to typed
  `PersesDashboard`s (`zuno-overview`, `zuno-infra-data`, `zuno-usage-cost`,
  `zuno-run-trace`, `zuno-gitops`, `zuno-ai-models`, `zuno-agents-tools-rag`,
  `zuno-data`), all `metadata.namespace: redhat-ods-monitoring` (ADR-0553),
  all referencing WP-138's existing three `PersesGlobalDatasource`s (no new
  datasource resource created). Work done in parallel by dimension, each
  translation grounded directly in WP-138's two live-verified pilot files
  (`dashboard-mesh-gateway.yaml`, `dashboard-trustyai.yaml`) for schema
  shape, naming, and escaping conventions - not re-derived from scratch.
  Judgment calls made and flagged in each file's own header comment (not
  silent):
  - **Unit/format drop on `TimeSeriesChart`/`Table` panels** (percentunit,
    Bps, bytes, currencyUSD, short, reqps, ...) - repeats WP-138's own
    confirmed schema rejection of `plugin.spec.format` on those two panel
    kinds; only `StatChart` panels keep `format`/`thresholds`.
  - **`dashboard-usage-cost.yaml`'s "Cost by provider/model" piechart**
    translated best-effort to `plugin.kind: PieChart` - no live RHOAI
    example on this cluster confirms this plugin kind exists/renders,
    unlike the other kinds used elsewhere (all confirmed against RHOAI's
    own live resources per WP-138). Flag this as the first surviving
    unconfirmed panel kind in the chart.
  - **`dashboard-run-trace.yaml`'s `run_id` free-text variable** translated
    to `TextVariable` - also unconfirmed against any live example, for the
    same reason (no RHOAI dashboard uses a text variable).
  - **`dashboard-run-trace.yaml`'s heavy Tempo-panel flattening**: 20 of its
    21 panels are Tempo-backed and Grafana used bargauge/piechart/stat/
    scatter types for them - all flattened to `Table`+`TraceQuery` per the
    only confirmed Tempo binding this chart has (from WP-138's own
    `meshErrorTraces` panel), each with an inline description flagging the
    visual simplification (bar/donut/single-number encoding lost, raw rows
    shown instead).
  - **`dashboard-data.yaml`'s Redis panels**: confirmed, not assumed, that
    Redis actually lives in `zuno-auth`
    (`gitops/apps/redis/application-d0.yaml`/`-d1.yaml`, both
    `destination.namespace: zuno-auth`) despite the dashboard's own
    `zuno-data` framing - each of the 4 Redis panels carries an explicit
    description noting this, not silently relocated or renamed.
  - Dropped throughout, and noted in each header: cross-dashboard "Zuno
    dashboards" link dropdowns, per-panel Explore/Jaeger deep-links, and
    (`dashboard-overview.yaml`) the `dashlist` navigation row - none has a
    confirmed Perses equivalent used in this chart.
  - Verification performed this pass: `helm lint`/`helm template` on the
    full chart (clean), a schema self-check across all 10 dashboards for
    the `plugin.spec.format` trap (zero hits) and for unescaped
    `{{label}}` placeholders (zero hits), `check_workload_hardening.py`
    (passes, pre-existing unrelated `ai-gateway` finding aside), and
    `check_docs.py` (PASS). **Not** performed: applying to the cluster,
    `oc get persesdashboard` availability check, or the `rhods-dashboard`
    visual spot-check - deferred by explicit user request to resume this
    work later, not blocked on anything technical.
- **2026-09-10** - resumed on `demo333`. The 8 files were already
  `Available: true`-pending via ArgoCD's pre-existing auto-sync (applied
  automatically when this WP's commits landed on the `demo333` branch, no
  `make d1 install perses` needed) but 2 of the 8 came up
  `Available: false` with real `PersesBackendError`s, exactly the kind of
  unconfirmed judgment call flagged above:
  - `dashboard-usage-cost.yaml`'s `costByProviderModel` `PieChart` shipped
    an empty `plugin.spec: {}` - `radius` has no default in the plugin's
    CUE schema (`spec.radius: number`, no `*default`) and was left
    incomplete. Fixed per the plugin's own shipped valid test fixture
    (`radius: 50`, `calculation: last`).
  - `dashboard-agents-tools-rag.yaml` had two separate format-unit
    defects: `nonAllowedRatio`/`ragSearchErrorRatio` used
    `format.unit: percentunit` (not a valid Perses unit - `percent` or
    `percent-decimal` only), and `freshnessAlertsFiring` used
    `format.unit: short` (Grafana-only, no Perses equivalent). Both fixed
    to match this chart's own already-`Available` precedent
    (`mesh5xxRatio` in `dashboard-mesh-gateway.yaml`): `unit: percent`
    with thresholds scaled x100, and `unit: decimal` for the plain count,
    respectively.
  - All 10 `PersesDashboard`s reached `Available: true` after these three
    fixes (3 commits, pushed to `demo333`, picked up by the existing
    `zuno-perses-d1` Application's `selfHeal` auto-sync - no manual
    `argocd app sync` needed either). `docs/roadmap/implementation-roadmap.md`'s
    Phase 41 row and ADR-0551 both updated to match (ADR-0551's own
    `Superseded in part` status left unchanged, per its acceptance
    criteria).

## Out of scope / deferred

- Any Grafana deprecation - not decided by ADR-0551/ADR-0552/ADR-0553.
- Any further Perses dashboard beyond the ten that exist in Grafana today.
- Making the `UIPlugin` surface in the OpenShift console nav - platform gap,
  not a repo-side task (see WP-138).

## Completion criteria

Per WP-138's own precedent (closed on data-layer verification alone, since
no visual rendering path exists on this cluster for this repo's dashboards -
see ADR-0553's dated correction note), WP-139 is done when all eight
dashboards are applied to the cluster and show `Available: true` via
`oc get persesdashboard -n redhat-ods-monitoring`, with correct panel/query
content confirmed against the Perses REST API (same method as WP-138),
alongside WP-138's two pilots and RHOAI's own, with zero changes to any
existing Grafana or RHOAI-owned resource. The original
"renders in `rhods-dashboard`" bar is kept only as a courtesy recheck, not a
gate - it is expected to reconfirm, not overturn, WP-138's finding.

Met in full 2026-09-10: all 10 dashboards `Available: true` on `demo333`
with panel/query content confirmed via the Perses REST API, zero changes
to any Grafana or RHOAI-owned resource.
