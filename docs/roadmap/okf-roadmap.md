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

- **OKF v0.1 — content excellence, in-repo** (ADR-0502 – 0504, 0511 – 0513,
  0515): the two-stage agent maturity model, the generated per-agent
  authorization matrix ("who can use what, for what, under which policy —
  and how much"), real `deployment/` content, the `tests/` target
  structure, per-conversation frontend tabs with one browser tab per
  agent, quota policy enforced via Kuadrant, project-bound tasks with
  Salesforce-verified context, and a real schema for
  `rag/`/`tools/`/`policies/` content. ADR-0505, the original per-task tab
  decision, was abandoned before implementation and superseded by
  ADR-0515. `agents/` stays in this repository throughout.
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

Order rationale: WP-43 (stages + READMEs) first — every later package
writes into the structure it fixes. WP-44/45/46 are independent once it
merges; WP-44 Part A unblocks the quota column (WP-54) and the
prompt-example schema (WP-061 soft). WP-54 → WP-55 is strict (the
binding's validity window and precedence live in quota policy). WP-47 is
Abandoned; WP-061 (its replacement, ADR-0515) is the phase's only
component-code package.

| WP | Brief | ADRs | Depends on | State | Operator actions remaining |
|---|---|---|---|---|---|
| WP-43 | [wp-43](work-packages/wp-43-agent-maturity-alignment.md) | 0502 | — | Done | none |
| WP-44 | [wp-44](work-packages/wp-44-okf-authorization-matrix.md) | 0503 (matrix) | WP-43 | Done | none |
| WP-45 | [wp-45](work-packages/wp-45-deployment-dir-content.md) | 0503 (deployment) | WP-43 | Done | none |
| WP-46 | [wp-46](work-packages/wp-46-tests-target-structure.md) | 0504 | WP-43 | Done | none |
| WP-47 | [wp-47](work-packages/wp-47-task-tabs-frontend.md) | 0505 | soft: WP-44A, ADR-0212 state | Abandoned | superseded by WP-061 (ADR-0515); no code was written |
| WP-061 | [wp-061](work-packages/wp-061-per-conversation-tabs-frontend.md) | 0515 | WP-44A | Operator pending (repo work merged) | rebuild/redeploy 3 components; cross-agent tab-reuse + drag-reorder + hard-delete demo |
| WP-54 | [wp-54](work-packages/wp-54-quota-policy-and-kuadrant-translation.md) | 0511 | WP-44A | Operator pending (2026-08-21 — blocked on an external Kuadrant wasm-shim defect, see brief) | live 429 demo — blocked until Red Hat fixes the Connectivity Link wasm-shim (not a repo/config gap) |
| WP-55 | [wp-55](work-packages/wp-55-project-bound-tasks.md) | 0512 | WP-54 (+WP-061A rec.) | Not started | live Salesforce bind/deny pass (needs sandbox creds — WP-22/33 gap) |
| WP-56 | [wp-56](work-packages/wp-56-rag-tools-policies-schema.md) | 0513 | WP-43 | Done | none |

### Phase 2 — OKF v0.2: extraction

Order rationale: strictly mirror (WP-48) → pin (WP-49) → cutover
(WP-50), so image builds are never without a working content source;
WP-51 (hooks) needs only the pin and runs in parallel with the cutover.
The cross-repo single-writer clause is in force from WP-48's merge to
WP-50's.

| WP | Brief | ADRs | Depends on | State | Operator actions remaining |
|---|---|---|---|---|---|
| WP-48 | [wp-48](work-packages/wp-48-okf-repo-bootstrap.md) | 0506 (start) | WP-44, WP-45, WP-46 | Not started | create zuno-okf repo + protection + CODEOWNERS (blocking precondition) |
| WP-49 | [wp-49](work-packages/wp-49-pinned-ref-builds.md) | 0507 | WP-48 | Not started | read-only CI credential for zuno-okf; one signed-bundle verification |
| WP-50 | [wp-50](work-packages/wp-50-okf-extraction-cutover.md) | 0506+0507 (close) | WP-49 | Not started | one ArgoCD sync cycle + one evaluation run post-cutover |
| WP-51 | [wp-51](work-packages/wp-51-adaptation-hooks-conformance.md) | 0508 | WP-49 (∥ WP-50) | Not started | none (deploys ride the next rollout) |

### Phase 3 — OKF v0.3: live reconciliation

Order rationale: mounts before watching — WP-52 must be **Done** (live
Naveo proof), not merely merged, before WP-53 starts; WP-53's Part B
demo pair is the stream's closing proof.

| WP | Brief | ADRs | Depends on | State | Operator actions remaining |
|---|---|---|---|---|---|
| WP-52 | [wp-52](work-packages/wp-52-mounted-okf-artifacts.md) | 0509 | WP-50, WP-51 | Not started | deploy operator + Naveo chart bump; mounted-content confirmation |
| WP-53 | [wp-53](work-packages/wp-53-okf-live-reconciliation.md) | 0510 | WP-52 Done | Not started | two live demos (prompt propagation; ceiling violation); stream sign-off |

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

- 2026-08-18 — roadmap created alongside ADR-0501; tracker rows land with
  their WP briefs.
- 2026-08-19 — WP-56 (ADR-0513: real schema for `rag/`/`tools/`/`policies/`)
  added and executed against Tekos.
- 2026-08-21 — WP-47 (ADR-0505: per-task tabs) abandoned before
  implementation; replaced by WP-061 (ADR-0515: per-conversation tabs,
  one browser tab per agent).
