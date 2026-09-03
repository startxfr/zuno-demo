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

- **OKF v0.1 — content excellence, in-repo** (ADR-0502 – 0504, 0513,
  0515): the two-stage agent maturity model, the generated per-agent
  authorization matrix ("who can use what, for what, under which policy —
  and how much"), real `deployment/` content, the `tests/` target
  structure, per-conversation frontend tabs with one browser tab per
  agent, and a real schema for `rag/`/`tools/`/`policies/` content.
  ADR-0505, the original per-task tab decision, was abandoned before
  implementation and superseded by ADR-0515. `agents/` stays in this
  repository throughout. ADR-0511 (quota policy enforced via Kuadrant)
  and ADR-0512 (project-bound tasks with Salesforce-verified context)
  retargeted out of this milestone on 2026-08-24, first briefly to
  platform v0.3, then the same day to the new platform v0.5 milestone
  ("make the MaaS governance plane live and used by agents") — see
  change log; WP-54/WP-55 stay tracked in this file's own Tracker below,
  only their ADRs' version `Target` moved.
- **OKF v0.2 — extraction** (ADR-0506 – 0508): the `zuno-okf` repository is
  bootstrapped (history-preserving), this repository consumes it through a
  single pinned reference (baked-image build model unchanged), then the
  moved content is cut over out of this repository; every consuming
  component isolates its OKF parsing behind one adaptation hook validated
  by a shared conformance suite. ADR-0506/ADR-0507/ADR-0508 retargeted out
  of this milestone to platform v0.7 on 2026-08-30 (all `Proposed`,
  gated on an owner-created `zuno-okf` repository not yet provisioned) —
  see change log; WP-48/WP-49/WP-50/WP-51 stay tracked in this file's own
  Tracker below, only their ADRs' version `Target` moved.
- **OKF v0.3 — live reconciliation** (ADR-0509 – 0510): OKF content reaches
  running components as operator-materialized mounted artifacts instead of
  baked image copies, and the AIAgent operator watches the `zuno-okf`
  repository to reconcile running agent configuration within CR-declared
  boundaries. ADR-0509/ADR-0510 retargeted out of this milestone to
  platform v0.7 on 2026-08-30 alongside ADR-0506–0508 — see change log;
  WP-52/WP-53 stay tracked in this file's own Tracker below, only their
  ADRs' version `Target` moved.

## Execution model

Inherited unchanged from the
[implementation roadmap](implementation-roadmap.md):

- **1 WP = 1 brief = 1 reviewable change-set** (large WPs split into
  lettered parts, each independently committable).
- Every brief separates **repo changes** from **operator/human steps**;
  repo work merging moves the ADR to `Partially implemented` with residual
  operator actions enumerated in the ADR body; listed operator
  confirmations move it to `Implemented`. ADRs with no operator dependency
  go straight to `Implemented` on merge.
- **WP state machine:** `Not started → Repo work in review → Repo work
  merged → Operator pending → Done`, plus three terminal states for work that
  stops early: `Abandoned` (superseded by another decision), `Cancelled`
  (deprioritized), `Closed — deferred` (blocked outside this repo). A WP that
  merged code but was then superseded is `Abandoned`, and its brief must say
  what landed - see WP-065/WP-066. `Done` requires the brief's
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

**Moved (2026-09-03).** The OKF work packages are tracked in the single
[implementation roadmap](implementation-roadmap.md), phases 33–35:

| Was | Now |
|---|---|
| Phase 1 — OKF v0.1: content excellence | [Phase 33 — OKF: content excellence](implementation-roadmap.md#phase-33--okf-content-excellence) |
| Phase 2 — OKF v0.2: extraction | [Phase 34 — OKF: extraction](implementation-roadmap.md#phase-34--okf-extraction) |
| Phase 3 — OKF v0.3: live reconciliation | [Phase 35 — OKF: live reconciliation](implementation-roadmap.md#phase-35--okf-live-reconciliation) |

Two trackers had become one tracker's worth of truth: ADR-0506–ADR-0510 were
retargeted to platform v0.7 on 2026-08-30, so WP-48–WP-53 sat under phase
headings ("OKF v0.2", "OKF v0.3") naming milestones their own ADRs no longer
targeted. The milestone narrative below is still current and still owns the
OKF *version line*; only the WP tables moved.

## Dependency graph

```text
WP-43 ─┬─ WP-44 ─┬──────────────┬─ WP-48 ── WP-49 ─┬─ WP-50 ─┬─ WP-52 ── WP-53
       │         │              │                  └─ WP-51 ─┘
       ├─ WP-45 ─┤              │
       ├─ WP-46 ─┘              │
       │         (WP-44A soft) ─┴─ WP-061  (WP-47 abandoned)
       ├─ WP-44A ── WP-54 ── WP-55
       └─ WP-56
```

## Change log

- 2026-08-30 — ADR-0506, ADR-0507, ADR-0508 (OKF v0.2 -> v0.7) and
  ADR-0509, ADR-0510 (OKF v0.3 -> v0.7) retargeted to the platform
  roadmap's v0.7 band, alongside its other not-yet-started work
  (ADR-0352, ADR-0534). All five ADRs are `Proposed`, all six WPs
  (WP-48–WP-53) are `Not started`; there is no repo-side blocker — WP-48's
  own dependencies (WP-44/45/46) are all `Done` — only the operator step
  of provisioning the `zuno-okf` GitHub repository (branch protection +
  CODEOWNERS) is outstanding. Docs-only move, following the precedent set
  when ADR-0511/ADR-0512 left OKF v0.1 for the platform bands: WP-48
  through WP-53 stay tracked in this file's own Tracker; only the ADRs'
  `Target` moved. See `docs/adr/README.md`'s matching Retargeting note and
  `docs/roadmap/versions.md`.
- 2026-08-25 — WP-54 closed `Done`, ADR-0511 `Implemented`. The
  429-exceedance acceptance run passed live with a real token
  (`intensive` 429 at request 11 against 10/5m, `standard` at 61 against
  60/5m, zero 5xx). The run was expected to be a formality and was not:
  it found three stacked defects that had left quota enforcement counting
  nothing while `RateLimitPolicy` still reported `Accepted`+`Enforced` and
  Limitador still held every compiled limit — a missing identity
  dynamic-metadata filter on the AuthPolicy, a CEL error-absorption rule
  the wasm-shim does not implement, and Kuadrant's predicate
  concatenation shredding an unparenthesized ternary. Because all three
  present as a clean `200`, the run is now a harness layer
  (`platform/testing/quota_429.py`, invoked by `day2_stresstest.py`)
  rather than an operator command, and the generator lints that every
  `auth.identity.*` field its counters read is actually published. See
  ADR-0511's 2026-08-25 implementation note.
- 2026-08-24 (evening) — WP-54's wasm-shim blocker retracted: root-caused
  by WP-071 to a locally-fixable Authorino/Envoy TLS trust mismatch, plus
  a second gap specific to this gateway (Kuadrant's own generated
  `EnvoyFilter` never adds TLS to the ext_authz cluster — fixed by a new,
  hand-authored `EnvoyFilter` mirroring the pattern RHOAI's
  `odh-model-controller` already uses for `maas-default-gateway`). Both
  fixed and live-verified 2026-08-24: `401`, not `500`, on
  `zuno-agent-gateway`. See ADR-0511's 2026-08-24 note and
  `implementation-roadmap.md`'s matching entry (WP-071 is
  tracked there, alongside WP-27, since it lives in that file's
  `work-packages/`).
- 2026-08-24 (afternoon) — ADR-0511/ADR-0512 moved a second time today,
  from the morning's platform v0.3 into the new platform v0.5 milestone
  ("make the MaaS governance plane live and used by agents"), created
  alongside v0.6 and v0.7 — see `docs/adr/README.md`'s afternoon
  Retargeting note and `versions.md`.
- 2026-08-24 (morning) — ADR-0511/ADR-0512 retargeted from OKF v0.1 to
  platform v0.3
  (see [implementation-roadmap.md](implementation-roadmap.md)'s
  own change log and `docs/adr/README.md`'s Retargeting note): WP-54 is
  stalled on the same upstream Kuadrant wasm-shim defect blocking WP-27/
  ADR-0201, and WP-55/ADR-0512 has a hard `Depends on: WP-54`, so it moves
  with it. This milestone's ADR-0501–0512 numbering band is unaffected —
  only the two ADRs' version `Target` moved out of the OKF v0.1 count.
  (Superseded same day — see the afternoon entry above.)
- 2026-08-18 — roadmap created alongside ADR-0501; tracker rows land with
  their WP briefs.
- 2026-08-19 — WP-56 (ADR-0513: real schema for `rag/`/`tools/`/`policies/`)
  added and executed against Tekos.
- 2026-08-21 — WP-47 (ADR-0505: per-task tabs) abandoned before
  implementation; replaced by WP-061 (ADR-0515: per-conversation tabs,
  one browser tab per agent).
