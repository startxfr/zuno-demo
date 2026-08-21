# WP-10: Model quality gates and LM-Eval (promotes ADR-0107 + ADR-0108)

- **State:** Operator pending (2026-08-18 - operator authorized the GPU LM-Eval run and the gated-promotion proof this pass. Gated promotion: `make d1 check agents` (the real ADR-0053 gate) ran live twice, both genuine, reproducible BLOCKED promotions (65-70% vs the 75% threshold) - the blocking half of the acceptance bar. A real regression was found and fixed as a byproduct: PgBouncer held a stale cached auth failure for `agentcheckpoints` after this session's WP-12 failover drill; restarting the PgBouncer pods fixed it (mandatory security checks went 6/7 -> 7/7). The passing-promotion half is open, not fabricated. LM-Eval: found and fixed three real 3.5.0-ea.2 TrustyAI operator bugs (`pvcManaged.size` reconciler panic on empty size; served-model-name isn't a valid HF tokenizer repo id; `allowOnline`/env-override are both silently ignored, worked around with an operator-populated `datasetCachePvc`), and right-sized the task after the full `mmlu` group's 56,168 requests 503'd the shared predictor mid-run. Got a real request past every one of those layers, then hit what this pass wrongly called a genuine mesh routing gap. 2026-08-21 correction: that 503 was actually a missing `NetworkPolicy` ingress rule for the lm-eval pod (`gitops/charts/models/templates/networkpolicy.yaml` only ever allowed `ai-gateway`/`rag-service`) - `/v1/chat/completions` failed identically, proving it wasn't path-specific, and the predictor was healthy the whole time (200 OK via loopback, nothing reaching its access log). Fixed the allow-list and automated the `lmeval-hf-cache` PVC prefetch that had also gone stale (now chart-managed, tokenizer sourced from this cluster's own S3 model bucket). A full `mmlu_abstract_algebra` run now completes end-to-end (100 samples, `acc: 0.57 ± 0.05`). Still `Operator pending`/both ADRs `Partially implemented`: the operator's own `LMEvalJob.status.state` never reflects the real completion (stays `Scheduled`, no `status.results`) - a fourth real 3.5.0-ea.2 operator bug - so `make d1 check models`'s Day 1 check still can't see a run as complete even though it now genuinely succeeds. See ADR-0108's dated notes.)
- **ADRs:** ADR-0107, ADR-0108 (Proposed -> To be implemented -> Partially implemented -> Implemented)
- **Depends on:** WP-00 (done)
- **Blocks:** WP-34 (eval gate reuse), WP-40
- **Estimated files touched:** ~8

> Execute this brief as a standalone task from the repository root. Two
> stub promotions, one implementation: 0107 is the gate policy, 0108 is the
> LM-Eval mechanism feeding it.

## Goal

Promote stubs ADR-0107 and ADR-0108 to full records, then (a) make agent
regression a blocking promotion gate built on the existing Tekos evaluation
harness, and (b) wire OpenShift AI LM-Eval (`LMEvalJob`) manifests for
candidate local-model comparison. GPU/cluster execution is the operator part.

## ADR references

Stub origins (`docs/adr/0100-v0.1-roadmap.md`): ADR-0107 blocks promotion when model/agent regression breaches agreed thresholds; ADR-0108 uses OpenShift AI evaluation capabilities to compare candidate local models.

Related: ADR-0027 (20 acceptance scenarios), ADR-0028 (75% threshold),
ADR-0053 (make check as acceptance/security gate), ADR-0019 (OpenShift AI
serving). Acceptance criteria: Standard clauses.

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- Read: `evaluations/tekos/run_acceptance_gate.py`, `gate_checks.py`,
  `scenarios.yaml`; `ansible/roles/openshift_ai/tasks/` (component wiring
  precedent — beware uncommitted ADR-0344 edits, see What NOT to touch);
  `gitops/charts/openshift-ai/values.yaml` (which DSC components are
  Managed).

## Step 0 — ADR promotions (two files, same procedure)

1. Create `docs/adr/0107-introduce-automated-model-quality-gates.md`
   (standard header, `- **Status:** To be implemented`, Target `v0.1`) with
   this Decision:

   > Promote this decision from a one-line v0.1-roadmap entry
   > (`0100-v0.1-roadmap.md`) to a full record.
   >
   > A model or agent change may only be promoted when the target agent's
   > ADR-0027 acceptance suite passes at the ADR-0028 threshold (75%)
   > against the candidate configuration, and no per-scenario security
   > check regresses. The gate consumes the machine-readable output of
   > `evaluations/<agent>/run_acceptance_gate.py` and blocks in CI for
   > repo-declared model/routing changes; cluster-side promotions consume
   > the same artifact via the Day 1 check path. Thresholds are data
   > (per-agent configuration), not code.

2. Create `docs/adr/0108-automate-model-evaluation-with-lm-eval.md`
   (standard header, `- **Status:** To be implemented`, Target `v0.1`) with
   this Decision:

   > Promote this decision from a one-line v0.1-roadmap entry
   > (`0100-v0.1-roadmap.md`) to a full record.
   >
   > Use OpenShift AI's LM-Eval capability (`LMEvalJob` resources on the
   > DataScienceCluster's evaluation component) to benchmark candidate
   > local models on declared task suites before they become routable
   > (ADR-0021 classes). Job manifests and task selections are
   > GitOps-managed; results land in the model quality gate (ADR-0107) as
   > one of its inputs. LM-Eval complements — never replaces — the
   > per-agent ADR-0027 acceptance suites.

   Both files end with the Standard-clauses pointer and Related ADRs
   (0107: 0027, 0028, 0053, 0108; 0108: 0019, 0021, 0107).
3. In `docs/adr/0100-v0.1-roadmap.md`: KEEP both `### ADR-0107:`/`### ADR-0108:`
   headings; replace each body with the promotion pointer line to its new file
   (`Promoted to a full decision record: see [ADR-0107](0107-introduce-automated-model-quality-gates.md) (WP-10 implementation).` etc.).
4. In `docs/adr/README.md`: flip both rows to direct links; statuses
   `Proposed` → `To be implemented`.
5. `python3 platform/docs/check_docs.py` must exit 0 before continuing.

## Repo changes (step by step)

1. **Gate runner:** `evaluations/quality_gate.py` — takes an agent name and
   a candidate label, runs `evaluations/<agent>/run_acceptance_gate.py`,
   compares against the per-agent threshold config (new
   `evaluations/<agent>/gate_config.yaml`, seeded for tekos at 0.75), exits
   non-zero on breach. Reuse `gate_checks.py` logic — do not reimplement.
2. **CI wiring:** lint.yml job running the gate for agents whose evaluation
   inputs changed in the PR (path filter); blocking.
3. **LMEvalJob manifests:** `gitops/charts/openshift-ai/templates/` (or a
   dedicated `gitops/charts/lm-eval/` if the openshift-ai chart is
   operator-config-only — mirror whichever pattern the chart uses for other
   optional resources), parameterized by model + task suite in values;
   ensure the DSC component that provides LM-Eval is `Managed` (check
   `values.yaml`; add if missing).
4. **Day 1 check:** extend the models/agents check path so a completed
   LMEvalJob's results are readable via `make d1 check models` (follow
   `ansible/roles/models/tasks/` conventions).
5. **Tests:** gate passes/fails on synthetic result fixtures; threshold read
   from config; unknown agent fails closed.

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set
  (**`ansible/roles/openshift_ai/` is in it** — if `git status` still shows
  it modified, stop and ask before editing that role).
- `evaluations/tekos/scenarios.yaml` content (gate consumes, not edits).
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m py_compile evaluations/quality_gate.py`
- `python3 -m pytest evaluations/ -q` (add tests dir if absent)
- `helm lint gitops/charts/openshift-ai` (and `lm-eval` chart if created)
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up (not executable by the model)

1. Operator: run an `LMEvalJob` on the GPU cluster for one candidate model;
   confirm results flow into the gate artifact — discharges ADR-0108.
2. Operator: exercise one blocked promotion (candidate below threshold) and
   one passing promotion — discharges ADR-0107's blocking claim end to end.

## Status updates (then re-run check_docs.py)

- After repo merge: both ADRs →
  `Partially implemented (gate runner, CI wiring and LMEvalJob manifests merged; GPU cluster runs pending)`;
  index rows to match; tracker → `Operator pending`; this file's State.
- After operator runs: ADR-0107 → `Implemented - see \`evaluations/quality_gate.py\`.`;
  ADR-0108 → `Implemented - see \`gitops/charts/openshift-ai/\`.`; index rows
  `Implemented`; tracker → `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- Continuous benchmarking across models (WP-40 / ADR-0305).
- The MLOps pipeline's use of the gate (WP-34 consumes `quality_gate.py`).
