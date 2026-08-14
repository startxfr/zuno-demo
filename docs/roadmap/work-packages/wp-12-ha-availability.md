# WP-12: HA and the 99.9% availability objective (promotes ADR-0101 + ADR-0102)

- **State:** Repo work merged (2026-08-14 - ADR-0101/0102 promoted to full records. PDB + topologySpreadConstraints added to agent-runtime/ai-gateway/mcp-gateway/rag-service (soft ScheduleAnyway constraint, safe at the current demo replicas: 1) and to Keycloak's CR (`spec.scheduling`, schema-verified via `oc explain`); PostgreSQL/Redis were already replica/PDB-complete via PGO/Bitnami defaults (confirmed live) - only topologySpreadConstraints was missing there. `check_workload_hardening.py` gained availability checks (116/116 passing). `docs/platform/slo.md` defines the 99.9% SLO, burn-rate alerting (`prometheusrule-slo.yaml`, disabled by default) and error-budget policy - honestly flags that `agent-bff` doesn't yet emit the needed request metric and the OTel Collector's metrics pipeline (now gained a `prometheus` exporter) isn't yet confirmed scraped by a live Prometheus. Both ADRs stay Partially implemented pending the operator steps below.)
- **ADRs:** ADR-0101, ADR-0102 (Proposed -> To be implemented -> Partially implemented -> Implemented)
- **Depends on:** WP-00 (done)
- **Estimated files touched:** ~12 (small edits across many charts)

> Execute this brief as a standalone task from the repository root. Two stub
> promotions, one implementation: 0101 is the HA mechanics, 0102 is the
> measured objective on top of them.

## Goal

Promote stubs ADR-0101 and ADR-0102, then give every shared platform service
production-oriented availability configuration (replicas, PodDisruptionBudget,
topology spread, probes) and define the 99.9% objective as measurable SLOs
with alerting rules. Failover and SLO measurement on a real cluster are the
operator part.

## ADR references

Stub origins (`docs/adr/0100-v0.1-roadmap.md`): ADR-0101 runs shared runtime, gateway, identity, data and observability services with production-oriented availability; ADR-0102 adopts 99.9% as the industrialized service objective.

Related: ADR-0015 (PostgreSQL platform), ADR-0012 (Keycloak), ADR-0029
(observability instrumentation), ADR-0112/WP-13 (recovery is the
counterpart). Acceptance criteria: Standard clauses.

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- Inventory the shared-service charts and their current replica/PDB state:
  `grep -rln "replicas" gitops/charts/{postgresql,keycloak,vault,redis,agent-runtime,ai-gateway,mcp-gateway,rag-service,observability}/ 2>/dev/null`
  and check which have `PodDisruptionBudget` templates. The authoritative
  scope list is: agent-runtime, ai-gateway, mcp-gateway, rag-service
  (runtime/gateways); keycloak (identity); postgresql, redis (data); the
  observability stack charts.
- Read: `platform/security/check_workload_hardening.py` (add availability
  checks in its style), `gitops/charts/observability/` (where
  PrometheusRule-style resources live, if any).

## Step 0 — ADR promotions

1. Create `docs/adr/0101-provide-ha-for-shared-agent-platform-services.md`
   (standard header, `- **Status:** To be implemented`, Target `v0.1`) with
   this Decision:

   > Promote this decision from a one-line v0.1-roadmap entry
   > (`0100-v0.1-roadmap.md`) to a full record.
   >
   > Every shared platform service (Agent Runtime, AI Gateway, MCP Gateway,
   > rag-service, Keycloak, PostgreSQL, Redis, and the observability stack)
   > runs with production-oriented availability configuration: >=2 replicas
   > where the workload supports it (PostgreSQL via its operator's HA
   > mechanism), a PodDisruptionBudget, topology spread across nodes, and
   > liveness/readiness probes. Availability configuration is chart values,
   > per environment; the demo profile may scale down, but the chart
   > defaults document the HA-capable shape and CI checks enforce that the
   > mechanisms exist in every in-scope chart.

2. Create `docs/adr/0102-target-99-9-percent-platform-availability.md`
   (standard header, `- **Status:** To be implemented`, Target `v0.1`) with
   this Decision:

   > Promote this decision from a one-line v0.1-roadmap entry
   > (`0100-v0.1-roadmap.md`) to a full record.
   >
   > Adopt 99.9% monthly availability as the industrialized objective for
   > the user-facing agent path (frontend -> BFF -> Agent Runtime -> AI
   > Gateway -> model). The SLO is defined in
   > `docs/platform/slo.md` with its measurement query (successful
   > request ratio at the BFF boundary), error-budget policy, and alerting
   > rules shipped as PrometheusRule resources in the observability chart.
   > The objective is a measured target: the ADR is implemented when the
   > SLO is defined, measured and alerted on a live cluster — not when the
   > number is merely written down.

   Both end with Standard-clauses pointer + Related ADRs (0101: 0012, 0015,
   0029, 0102, 0112; 0102: 0029, 0101).
3. `docs/adr/0100-v0.1-roadmap.md`: KEEP both headings; bodies → promotion
   pointer lines to the two new files (`(WP-12 implementation)`).
4. `docs/adr/README.md`: both rows → direct links, `To be implemented`.
5. `python3 platform/docs/check_docs.py` exits 0.

## Repo changes (step by step)

1. For each in-scope chart: add/parameterize `replicaCount` (default
   documenting the HA shape, demo overrides allowed), a
   `PodDisruptionBudget` template, `topologySpreadConstraints`, and confirm
   probes exist. Mirror the best-formed existing chart rather than inventing
   a new pattern; PostgreSQL HA goes through the operator's cluster spec
   (`gitops/charts/postgresql` values), not naive replicas.
2. Add availability checks (PDB present, probes present for in-scope charts)
   to `platform/security/check_workload_hardening.py` following its style.
3. Write `docs/platform/slo.md` (SLO definition, measurement query,
   error-budget policy) and add PrometheusRule alert resources to the
   observability chart.

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set.
- Actual demo-environment replica counts if a values override exists —
  change defaults/templates, not the demo profile's resource footprint,
  unless the user asks.
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `helm lint` + `helm template` on every touched chart (PDB renders)
- `python3 platform/security/check_workload_hardening.py` (exit 0 with the new checks)
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`
- `test -f docs/platform/slo.md`

## Operator / human follow-up (not executable by the model)

1. Operator: scale the HA profile up on cluster, run a node-drain/failover
   drill per service — discharges ADR-0101's availability claim.
2. Operator: confirm the SLO recording/alerting rules evaluate on the live
   monitoring stack over a measurement window — required before ADR-0102 can
   claim Implemented.

## Status updates (then re-run check_docs.py)

- After repo merge: both ADRs →
  `Partially implemented (HA chart mechanics, SLO definition and alert rules merged; failover drill and live measurement pending)`;
  index rows to match; tracker → `Operator pending`.
- After operator drills/measurement: ADR-0101 →
  `Implemented - see \`gitops/charts/\` PDB/topology templates.`; ADR-0102 →
  `Implemented - see \`docs/platform/slo.md\`.`; index rows `Implemented`;
  tracker → `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- Backup/recovery drills (WP-13 / ADR-0112).
- Multi-cluster/DR topologies (would need a new ADR).
