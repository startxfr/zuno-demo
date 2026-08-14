# WP-40: Automated benchmarking and routing optimization (promotes ADR-0305 + ADR-0304)

- **State:** Not started
- **ADRs:** ADR-0305, ADR-0304 (Proposed -> To be implemented -> Partially implemented -> Implemented)
- **Depends on:** WP-10 (merged), WP-34 (merged); WP-39 useful but not required
- **Blocks:** WP-42
- **Estimated files touched:** ~9 (two parts: 0305 first, 0304 second)

> Execute this brief as a standalone task from the repository root. Order
> matters: benchmarking (0305) produces the signals routing optimization
> (0304) consumes.

## Goal

Promote both stubs, then: (Part A, ADR-0305) a benchmark harness that runs
candidate models/adapters through LM-Eval suites + per-agent gates and
stores comparable results; (Part B, ADR-0304) a reviewed routing-policy
update flow that uses those results plus operational quality/cost/latency
signals — routing changes remain GitOps-reviewed, not autonomous (autonomy
is ADR-0309/WP-42).

## ADR references

Stubs (verbatim, from `docs/adr/0300-v0.3-roadmap.md`):
- ADR-0305: "Benchmark candidate models before routing-policy promotion."
- ADR-0304: "Continuously improve routing using measured operational and evaluation signals."

Boundaries: ADR-0301/0302 explicitly excluded these; ADR-0309/WP-42 owns
*autonomous* tuning under governance — here every routing change is a
human-reviewed PR.

## Preconditions

- WP-10 (LM-Eval + quality gate) and WP-34 (registry/pipeline) merged.
- `python3 platform/docs/check_docs.py` exits 0.
- Read: `evaluations/quality_gate.py`, the LMEvalJob manifests (WP-10),
  `policies/model-routing/`, `components/ai-gateway/app/` (where latency/
  cost/usage metrics are emitted — ADR-0029 instrumentation).

## Step 0 — ADR promotions

1. `docs/adr/0305-introduce-automated-model-benchmarking.md`
   (standard header, `- **Status:** To be implemented`, Target `v0.3`).
   Decision: promotion sentence + stub text, then: "Every candidate model or
   adapter is benchmarked before routing-policy promotion: LM-Eval task
   suites (ADR-0108) plus the target agents' acceptance gates (ADR-0107),
   producing a versioned, comparable result artifact stored alongside the
   Model Registry entry. A candidate without a benchmark artifact cannot be
   referenced by a routing-policy change." Related: 0107, 0108, 0302, 0304.
2. `docs/adr/0304-optimize-model-selection-using-quality-cost-and-latency.md`
   (same header pattern). Decision: promotion sentence + stub text, then:
   "Routing policy (`policies/model-routing/`) gains explicit
   quality/cost/latency objectives per task class; a reporting job compares
   live operational metrics (ADR-0029) and benchmark artifacts (ADR-0305)
   against those objectives and emits a recommended policy diff. Applying a
   recommendation is a normal reviewed GitOps change. No component changes
   routing autonomously (that is ADR-0309's separately governed scope)."
   Related: 0021, 0029, 0303, 0305, 0309.
3. `docs/adr/0300-v0.3-roadmap.md`: KEEP both headings; bodies → promotion
   pointer lines (`(WP-40 implementation)`).
4. `docs/adr/README.md`: both rows → direct links, `To be implemented`.
5. `python3 platform/docs/check_docs.py` exits 0.

## Repo changes

1. **Part A:** `evaluations/benchmark.py` — orchestrates LM-Eval runs +
   agent gates for a candidate, writes the versioned result artifact
   (schema documented in the file); registry-entry linkage; fixture tests.
   Enforce the no-artifact-no-promotion rule in the WP-10 CI gate.
2. **Part B:** objectives blocks in `policies/model-routing/` (per task
   class: quality floor, cost ceiling, latency target);
   `evaluations/routing_report.py` — consumes metrics export + benchmark
   artifacts, emits the recommended diff as a report file (no writes to
   policy); fixture tests proving a regression produces a downgrade
   recommendation and an improvement produces an upgrade one.

## What NOT to touch

Standard list; plus: nothing writes to `policies/model-routing/`
automatically; `evaluations/*/scenarios.yaml` content unchanged.

## Acceptance checks

- `python3 -m pytest evaluations/ -q`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up

1. Operator: run a full benchmark for one real candidate on the GPU cluster;
   generate a routing report from live metrics; user reviews and merges (or
   rejects) the recommended policy diff — one full loop discharges both
   ADRs.

## Status updates (then re-run check_docs.py)

- After merge: both →
  `Partially implemented (benchmark harness, objectives and reporting merged; live loop pending)`;
  after the operator loop: ADR-0305 → `Implemented - see \`evaluations/benchmark.py\`.`;
  ADR-0304 → `Implemented - see \`policies/model-routing/\`, \`evaluations/routing_report.py\`.`;
  index rows + tracker + MEMORY.md accordingly.

## Out of scope / deferred

- Autonomous application of recommendations (WP-42 / ADR-0309).
