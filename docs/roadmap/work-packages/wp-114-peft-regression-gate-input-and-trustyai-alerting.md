# WP-114: PEFT regression as a hard promotion-gate input + TrustyAI alerting

- **State:** Not started (2026-09-02)
- **ADRs:** [ADR-0107](../../adr/0107-introduce-automated-model-quality-gates.md) (the gate this
  extends), [ADR-0534](../../adr/0534-integrate-trustyai-for-ai-evaluation-and-guardrails.md)
  (Phase 3 - the regression rule being enforced), [ADR-0108](../../adr/0108-automate-model-evaluation-with-lm-eval.md)
  (declared LM-Eval results as an ADR-0107 input in its own Decision text - an input that was
  never actually wired until this WP)
- **Depends on:** WP-109 (Done - `evaluations/peft_regression.py` and the base/wesh LMEvalJob
  pair), WP-113 (Done - the metrics the alerts fire on)
- **Related:** WP-10 (the gate), WP-087 (the register/tool-calling halves whose "thresholds are
  data" extension pattern this follows)

## Goal

Two follow-ups WP-109/WP-113 explicitly deferred, now executed:

1. **Make ADR-0534 Phase 3 enforceable.** `evaluations/peft_regression.py` today is a standalone
   reporter: it produces a PASS/FAIL artifact that nothing consumes - a fine-tune with a real
   capability regression (wesh: mmlu `-0.12` vs the `0.05` threshold, WP-109 open finding) can
   still be promoted because no gate reads the verdict. This WP wires it into
   `evaluations/quality_gate.py` as a config-driven fourth input: a `peft_regression:` block in
   `evaluations/<agent>/gate_config.yaml` (data, not code - ADR-0107's own rule) names the
   base/candidate LMEvalJobs and threshold; when present, the check runs and is AND-ed into
   `overall`. `mlops.stage_evaluate` inherits it for free (it calls `quality_gate.evaluate()`),
   so the KFP pipeline's no-bypass enforcement now covers capability regression too.
2. **Alert on the TrustyAI metrics WP-113 made visible.** A `PrometheusRule` on the existing
   pattern (`gitops/charts/observability/templates/prometheusrule-slo.yaml`): Garak attack
   success rate above threshold, evaluation Job failures, RAGAS score floor. The Garak alert is
   expected to FIRE immediately (wesh MitigationBypass ASR = 1.0) - that firing is the live
   proof, not a nuisance to silence.

Wiring the gate onto an ALREADY-ADOPTED model forces the WP-109 open decision: wesh currently
fails the regression check while serving Comage's primary traffic. The mechanism for that
decision is a **waiver**: `compare()` gains config-driven, per-task/metric waivers carrying a
mandatory reason - an accepted trade-off stays visible in every report as WAIVED instead of
silently raising the global threshold. Whether wesh gets that waiver is the operator's call,
asked once the FAIL is demonstrated live.

## Steps

### Step 1 - waiver support in `peft_regression.compare()`
Optional `waivers` argument: `[{task, metric, max_regression, reason}]`. A failing metric matched
by a waiver whose own `max_regression` covers the delta becomes `ok=True` with
`waived: true` + the reason in the report. No waiver, or a delta beyond even the waiver's bound,
still fails. Tests extended (`evaluations/tests/test_peft_regression.py`).

### Step 2 - the gate half in `quality_gate.py`
`evaluate()` reads an optional `peft_regression:` config block (`base_job|base_file`,
`candidate_job|candidate_file`, `namespace`, `max_regression`, `candidate_label`, `waivers`).
When present: load both result sets (live `oc` path or file path), run `compare()`, AND the
verdict into `overall`, and carry the report in the result dict (additive keys only -
`peft_regression_ok`, `peft_regression`). Read failures raise `QualityGateError` (exit 2, fail
closed - a configured check that cannot run must never silently pass). Absent block = unchanged
behavior for every agent. Tests extended (`evaluations/tests/test_quality_gate.py`).

### Step 3 - configure it for comage
`evaluations/comage/gate_config.yaml` gains the block naming `qwen35-9b-mmlu` (base) vs
`qwen35-9b-wesh-mmlu` (candidate) - comage is wesh's primary consumer (ADR-0526 decision 7).
Tekos keeps no block: its primary model IS the base.

### Step 4 - TrustyAI PrometheusRule
`gitops/charts/observability/templates/prometheusrule-trustyai.yaml`: `GarakAttackSuccessHigh`
(last pushed ASR > 0.5), `TrustyAIEvalJobFailed` (garak/ragas Job failed), `RagasScoreLow`
(last score < 0.7). Severity ticket-level, ADR label 0534, `monitoring.coreos.com/v1` only.

### Step 5 - live test, then the wesh decision
Run the real gate (`python3 evaluations/quality_gate.py --agent comage`) against the live
cluster: expect the acceptance/register halves to pass and the peft half to FAIL on wesh's real
`-0.12` - proving the hard input works. Verify the PrometheusRule loads and
`GarakAttackSuccessHigh` actually fires. Then ask the operator: waiver for wesh (documented
trade-off, gate PASS restored, future candidates still gated) or leave the gate failing pending
a retrain decision.

## What NOT to touch

- `run_acceptance_gate.py` and the ADR-0053 `make check` path - unrelated gate, stays untouched.
- The global `max_regression` default (0.05) - waivers exist precisely so the threshold never
  gets relaxed globally to accommodate one model.
- `mlops.py` - inherits the new half through `quality_gate.evaluate()`, zero change.
- The gitignore on `evaluations/benchmarks/*.json` - the gate re-derives from live LMEvalJobs,
  it does not depend on the artifact being committed.

## Verification checklist (operator step - ask before running)

1. `python3 evaluations/tests/test_peft_regression.py` and `test_quality_gate.py` pass.
2. Live `quality_gate.py --agent comage` shows the peft half FAIL on real wesh data and
  `overall: FAIL` (exit 1) - then, if the waiver is granted, a rerun shows WAIVED + PASS.
3. `oc get prometheusrule zuno-trustyai -n zuno-monitoring` exists; `GarakAttackSuccessHigh`
   visible as firing/pending in the platform Alertmanager or via the Thanos rules API.
4. Agents without the config block: gate behavior byte-identical (tekos run or unit tests).

## Risks and known unknowns

1. LMEvalJob `status.results` is known to be empty on some operator-bug paths (ADR-0108) - the
   live read fails loudly (exit 2), which is correct fail-closed behavior but means the gate
   depends on the base/candidate benchmark pair being fresh and Complete/Succeeded.
2. The comage acceptance suite is a live 20-scenario run - the full gate takes minutes and GPU;
   this WP adds one `oc get` pair on top, negligible.
3. Alert thresholds (0.5 ASR, 0.7 RAGAS) are first-pass engineering values, expected to be tuned
   as observation accumulates - same posture as WP-087's tool-calling floors.

## Status updates (once live-verified)

- This WP's `State` moves to `Done` once the checklist passes, including the demonstrated live
  FAIL and the operator's wesh decision recorded (waiver or not).
