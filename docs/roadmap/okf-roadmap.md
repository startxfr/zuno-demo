# OKF stream implementation roadmap

**Purpose:** drive every ADR in the OKF stream (ADR-0501 – ADR-0512) to
`Implemented`. The work is decomposed into work packages (WPs), each with a
self-contained brief under [work-packages/](work-packages/) written so a
lower-capability model can execute it as a standalone task. The stream is
established by [ADR-0501](../adr/0501-establish-the-okf-stream-with-its-own-milestones-and-roadmap.md).

[docs/adr/README.md](../adr/README.md) is the **sole authority for ADR
status**. This roadmap tracks WP state only — never copy ADR status strings
here (`platform/docs/check_docs.py` validates the index/body pair; a third
copy would drift unvalidated).

## Milestones

- **OKF v0.1 — content excellence, in-repo** (ADR-0502 – 0505, 0511, 0512):
  the two-stage agent maturity model, the generated per-agent authorization
  matrix ("who can use what, for what, under which policy — and how much"),
  real `deployment/` content, the `tests/` target structure, per-agent task
  tabs in the frontend, quota policy enforced via Kuadrant, and
  project-bound tasks with Salesforce-verified context. `agents/` stays in
  this repository throughout.
- **OKF v0.2 — extraction** (ADR-0506 – 0508): the `zuno-okf` repository is
  bootstrapped (history-preserving), this repository consumes it through a
  single pinned reference (baked-image build model unchanged), then the
  moved content is cut over out of this repository; every consuming
  component isolates its OKF parsing behind one adaptation hook validated
  by a shared conformance suite.
- **OKF v0.3 — live reconciliation** (ADR-0509 – 0510): OKF content reaches
  running components as operator-materialized mounted artifacts instead of
  baked image copies, and the AIAgent operator watches the `zuno-okf`
  repository to reconcile running agent configuration within CR-declared
  boundaries.

## Execution model

Inherited unchanged from the
[v0.1 – v0.3 implementation roadmap](v0.1-v0.3-implementation-roadmap.md):

- **1 WP = 1 brief = 1 reviewable change-set** (large WPs split into
  lettered parts, each independently committable).
- Every brief separates **repo changes** from **operator/human steps**;
  repo work merging moves the ADR to `Partially implemented` with residual
  operator actions enumerated in the ADR body; listed operator
  confirmations move it to `Implemented`. ADRs with no operator dependency
  go straight to `Implemented` on merge.
- **WP state machine:** `Not started → Repo work in review → Repo work
  merged → Operator pending → Done`. `Done` requires the brief's
  Status-updates section executed (ADR body + index + tracker + brief +
  MEMORY.md) and `python3 platform/docs/check_docs.py` to pass.
- **Immutability boundary:** only ADR `**Status:**` lines, dated
  gap/progress lists, and promotion pointers are editable. A change of
  direction requires a superseding ADR, never an edit.
- **Standing rules** (the v0.1–v0.3 roadmap's list applies verbatim), plus
  one new **cross-repo clause**: once WP-48 bootstraps `zuno-okf`, every WP
  brief must state per step which repository it touches; until WP-50's
  cutover merges, `zuno-demo` remains authoritative for all OKF content and
  `zuno-okf` is a mirror — never edit the same content in both.

OKF-stream ADRs are authored as full standalone files from the start (no
stub promotion); "Step 0" in these briefs is therefore only the ADR Status
flip prescribed by each brief's Status-updates section.

## Tracker

Update the **State** column as WPs progress; everything else is fixed at
authoring time. States: `Not started | Repo work in review | Repo work
merged | Operator pending | Done`.

### Phase 1 — OKF v0.1: content excellence

| WP | Brief | ADRs | Depends on | State | Operator actions remaining |
|---|---|---|---|---|---|

### Phase 2 — OKF v0.2: extraction

| WP | Brief | ADRs | Depends on | State | Operator actions remaining |
|---|---|---|---|---|---|

### Phase 3 — OKF v0.3: live reconciliation

| WP | Brief | ADRs | Depends on | State | Operator actions remaining |
|---|---|---|---|---|---|

## Dependency graph

```text
WP-43 ─┬─ WP-44 ─┬──────────────┬─ WP-48 ── WP-49 ─┬─ WP-50 ─┬─ WP-52 ── WP-53
       │         │              │                  └─ WP-51 ─┘
       ├─ WP-45 ─┤              │
       ├─ WP-46 ─┘              │
       │         (WP-44A soft) ─┴─ WP-47
       └─ WP-44A ── WP-54 ── WP-55
```

## Change log

- 2026-08-18 — roadmap created alongside ADR-0501; tracker rows land with
  their WP briefs.
