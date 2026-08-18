# WP-53: OKF live reconciliation (promotes ADR-0510; closes the stream)

- **State:** Not started
- **ADRs:** ADR-0510
- **Depends on:** WP-52
- **Estimated files touched:** ~15 (A) + ~8 (B)

> Execute this brief as a standalone task from the repository root.
> The stream's closing proof is Part B's end-to-end demo — do not mark
> anything Done on repo work alone.

## Goal

The operator polls the configured zuno-okf tracking ref, re-renders
affected agents' mounted artifacts within CR-declared ceilings
(narrow-only), applies per-change-class rollout (hot reload vs rolling
restart), and reports it all through `OKFContentSynced` + events. Proof:
a merged zuno-okf prompt edit reaches running Naveo with no image
rebuild.

## ADR references

ADR-0510 clauses 1–5; ADR-0509 (the artifact machinery this drives);
ADR-0106 (signature gate unchanged).

## Preconditions (verify before starting)

- WP-52 Done (live Naveo mounted proof confirmed, not just merged).
- Read: `internal/controller/aiagent_controller.go`'s
  `SetupWithManager` + requeue pattern; `config.go` (`OperatorConfig`
  gains tracking ref + interval); ADR-0510's change-class and ceiling
  definitions.

## Repo changes (step by step)

**Part A — machinery:**
1. Git source: read-only poller (configured tracking ref + interval in
   `OperatorConfig`), SHA resolution, per-agent change detection
   (bundle path + referenced policy slices); isolated from the core
   reconcile loop (own goroutine/requeue source; git downtime degrades
   to staleness, never reconcile failure).
2. Ceiling check: set comparison of bundle declarations vs CR
   `groups`/`knowledgeDomains`/`toolCapabilities`; widening → render
   nothing, `OKFContentSynced: False` with named violation, event.
   Narrowing/neutral → re-render (signature-verified, ADR-0509 path).
3. Change-class handling from the artifact manifest: hot-class →
   artifact update only (hooks re-read on manifest hash change —
   component-side re-read lands here if WP-52 stubbed it);
   startup-class → rolling restart of exactly the affected owned
   Deployments.
4. Explicitly pinned CRs (full-form `okfBundleRef`) excluded from the
   tracking loop; audit trail: event per applied change with SHA pair,
   agent, class, action.
5. envtest with a fake git source: change detection, ceiling
   violation, both rollout classes, pinned exclusion, staleness on
   unreachable repo.

**Part B — closing proof:**
6. Demo runbook + execution: edit a Naveo prompt in zuno-okf → review
   → merge → operator applies within one poll interval → running Naveo
   answers with the new prompt; then a deliberate ceiling-violation PR
   → merged → running Naveo unaffected, condition names the violation.
   Record both event trails in the State log.

## What NOT to touch

Standard list; plus: Tekos and every `Baked`/pinned agent; the
ADR-0507 pin file's role for image builds (two knobs by design); no
webhook surface (optional later addition per the ADR).

## Acceptance checks

- envtest suite covers every step-5 path; operator suite coverage
  stays at or above its current level.
- Lint + `check_docs.py` green; chart-rendered operator config exposes
  tracking ref + interval as values.

## Operator / human follow-up (not executable by the model)

Execute Part B's two live demos (the happy path and the ceiling
violation); sign off the stream: with ADR-0501–0512 statuses settled,
add the okf-roadmap change-log closing entry.

## Status updates (then re-run check_docs.py)

On merge: ADR-0510 → `Partially implemented (watch/reconcile machinery
merged; live demo pending)`; after both demos → `Implemented - see
operator/aiagent-operator/ and the okf-roadmap closing entry.`; ADR-0501
→ `Implemented` when every other stream ADR is `Implemented`. Index +
tracker + MEMORY.md accordingly.

## Out of scope / deferred

- Webhook-driven sync. Tekos migration off plain manifests (its own
  decision if ever). Baked-fallback retirement.
