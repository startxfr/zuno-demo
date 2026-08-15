# WP-40: Automated benchmarking and routing optimization (promotes ADR-0305 + ADR-0304)

- **State:** Repo work merged (2026-08-15); live benchmark+report loop
  pending. Step 0 promoted both ADR-0305 and ADR-0304 verbatim.
  **Part A** (`evaluations/benchmark.py`): orchestrates an LM-Eval results
  read (`--lm-eval-results-file`, the primary/testable path - a local
  JSON snapshot shaped like an `LMEvalJob.status.results` field; the
  live-cluster alternative shells out to `oc get lmevaljob ... -o json`,
  no new Kubernetes-client dependency) plus per-agent
  `quality_gate.evaluate()` calls (reused unmodified, same "consume the
  machine-readable output, never reimplement" discipline that module
  already established for WP-10), and writes a versioned
  `evaluations/benchmarks/<candidate>.json` artifact. New
  `evaluations/benchmarks/README.md` + `.gitignore` entry (generated
  output, empty today - no WP-34 GPU-trained adapter exists yet to
  benchmark). The "no artifact, no promotion" rule
  (`--check-policy` mode, scanning `policies/model-routing/model-routing-policy.yaml`'s
  `adapters:` list against the benchmarks directory) is wired as a real,
  always-blocking step in `.github/workflows/lint.yml`'s `quality-gate`
  job (unlike the pre-existing scenario-rate smoke check there, this one
  needs no live cluster - both its inputs are committed-or-absent repo
  state - so it's a genuine gate, not a wiring check; passes trivially
  today since `adapters: []`). **Part B**: `policies/model-routing/model-routing-policy.yaml`
  gained a new `objectives: []` block (per agent/task "task class":
  `quality_floor`/`cost_ceiling_usd_per_1k`/`latency_target_ms_p95`,
  empty by default, commented example matching the `adapters:` block's
  own style). `evaluations/routing_report.py` compares live metrics
  (`--metrics-file` snapshot default per D13 - this repo's OTel Collector
  has no queryable long-term store wired in; `--prometheus-url` is a
  documented, deliberately-unimplemented operator seam, `NotImplementedError`
  rather than a faked empty result) and `evaluations/benchmarks/*.json`
  artifacts against those objectives, emitting recommendations
  (`downgrade` when live cost/latency violates a ceiling/target,
  `upgrade` when a non-incumbent benchmarked candidate clears the quality
  floor) as a report file - confirmed it never writes to the policy file
  itself (grep clean). Quality is compared at agent granularity
  (`quality_gate.py`'s own `scenario_rate` measurement granularity, not
  a finer per-task-class one) - a documented simplification, not false
  precision. 21 new tests (`test_benchmark.py`: 12, `test_check_policy_artifacts_*`
  fail-closed and pass cases included; `test_routing_report.py`: 10,
  including the WP's own two named acceptance cases - a regression
  produces a downgrade recommendation, an improvement produces an
  upgrade one) plus the full pre-existing `evaluations/` suite, all
  green - verified both via this repo's own established direct-script
  convention AND via real `pytest` collection (33/33 passed), confirming
  the brief's own literal `python3 -m pytest evaluations/ -q` acceptance
  command works once pytest is actually installed (not a repo dependency
  anywhere else, so not assumed present by default).
  `python3 platform/docs/check_docs.py` PASS.
- **ADRs:** ADR-0305, ADR-0304 (Partially implemented merged here -> Implemented after the live benchmark+report loop)
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
