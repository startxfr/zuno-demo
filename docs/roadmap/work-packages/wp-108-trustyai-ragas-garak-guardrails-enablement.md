# WP-108: TrustyAI generic RAGAS/Garak enablement and mcpGuardrailsMode flip

- **State:** Done — live-verified 2026-09-02 on demo222, with a major course-correction: the
  `mcpGuardrailsMode` flip was executed, proven destructive (it kills the LMEvalJob controller -
  see Live findings), and reverted the same hour; ADR-0534 amended in place. Delivered instead:
  a Garak smoke scan (operand-shipped image, real run against qwen through mesh TLS origination,
  report.jsonl+html produced, Job `succeeded=1`) and a standalone built-in guardrails detector
  (`GuardrailsOrchestrator` Ready/DeploymentReady/RouteReady, live PII detection proven: email +
  SSN both flagged at score 1.0 with exact offsets). RAGAS: no provider in this release train,
  moved to WP-109. `make d3 check trustyai-config` reports all of it green in one pass. Commits
  `fc7b9dd1` (flip), `9c99c3a8` (smoke tests), `806391b0` (revert + ADR amendment).
- **ADRs:** ADR-0534 (Accepted, Phase 2 - infrastructure half)
- **Depends on:** WP-107 (Done - baseline health check green, `trustyai-config` scaffold in place)
- **Related:** ADR-0107/WP-10 (the model quality gate this and WP-109 eventually feed)
- **Unblocks:** WP-109 (Zuno-specific guardrail wiring + PEFT/LoRA comparison)

## Goal

Turn on the guardrails half of the TrustyAI operand (`mcpGuardrailsMode: false -> true`) and add
RAGAS and Garak to `trustyai-config` as **generic, standalone evaluation frameworks** - proven to
run correctly on this cluster via smoke-test Jobs - without yet wiring either of them to real Zuno
agent traffic. This is the "configuration basique dans RHOAI" step: infrastructure and platform
capability, not yet agent-specific behaviour. Zuno-specific wiring is WP-109.

## Live findings (2026-09-02, execution)

1. **`mcpGuardrailsMode: true` is a destructive mode switch, NOT an enablement - flipped and
   REVERTED the same hour.** Two stacked discoveries:
   - The flip does not even apply through ArgoCD: `zuno-openshift-ai-d1` carries
     `ignoreDifferences: DataScienceCluster /spec` (the documented silent-no-op trap) - the values
     commit (`fc7b9dd1`) synced green and changed nothing. Applied live via
     `oc patch datasciencecluster zuno-dsc`.
   - The patch then redeployed the TrustyAI operator with `--enable-services NEMO_GUARDRAILS`
     **only**, versus `TAS,LMES,GORCH,NEMO_GUARDRAILS,EVALHUB` before (ReplicaSet args, both
     revisions read live) - i.e. it KILLED the LMEvalJob controller (a direct ADR-0108
     regression), EvalHub, TrustyAIService and GuardrailsOrchestrator, while `TrustyAIReady`
     stayed `True` throughout (the condition does not cover which services run). Reverted to
     `false` at ~13:00Z; the operator returned to the full service list.
   **Net understanding: the guardrails capability (GORCH + NeMo) was ALWAYS enabled at `false`;
   ADR-0534's "the guardrails half has never been turned on" premise was wrong.** On this operand
   version the flag means "run the operand as an MCP-guardrails-only service", and it must stay
   `false` as long as LM-Eval matters. ADR-0534 amended accordingly.
2. **The operand is far richer than the ADR assumed.** Live CRDs: `GuardrailsOrchestrator`,
   `NemoGuardrails`, `EvalHub` (with 8 OOTB benchmark collections incl. `safety-and-fairness-v1`,
   with weighted pass-criteria), `TrustyAIService`, `LMEvalJob`. The operator CSV ships images
   for: FMS guardrails orchestrator, built-in detectors, HF detector runtime, NeMo guardrails
   server, EvalHub (+MCP variant), and **Garak** (`odh-trustyai-garak-lls-provider-dsp`, garak CLI
   v0.15.0+rhaiv.2 confirmed by running the image live). The smoke tests therefore use
   operand-shipped components instead of the generic pip-installed Jobs this brief originally
   sketched.
3. **RAGAS has NO provider or image anywhere in this release train** - EvalHub collections use
   `lm_evaluation_harness`/`lighteval` providers, and the operator config adds
   `guidellm`/`ibm-clear`, nothing RAGAS. Per ADR-0534's own "prefer shipped frameworks" rule,
   RAGAS moves wholly to WP-109, evaluated against real RAG retrievals (the only input where it
   is meaningful anyway), via a custom-built image if the operand still lacks one then. This WP's
   deliverable set is: `mcpGuardrailsMode` on + Garak smoke + built-in guardrails detector smoke.
4. The Garak smoke Job reuses the `app.kubernetes.io/name: lm-eval` label so WP-10's existing
   qwen NetworkPolicy 8000-ingress allowance admits it - no NetworkPolicy widened for a smoke
   test. A dedicated `trustyai-eval` identity + rule is WP-109's call.

## Why split this from WP-109

RAGAS and Garak are new to this repository (unlike LM-Eval, already proven by ADR-0108/WP-10).
Flipping `mcpGuardrailsMode` and standing up two new evaluation frameworks at the same time as
wiring them into the live Agent Runtime request path multiplies the number of unknowns in a single
change. This WP isolates "does the platform capability work at all" from "is it correctly and
safely wired to production agent traffic" (WP-109), the same separation ADR-0524/WP-085 used
between installing the Lightspeed operator and wiring it to Zuno's MCP Gateway/Keycloak/MaaS.

## Component and file layout

Builds on WP-107's `trustyai-config` scaffold - no new component, no new Application pair.

| | `openshift-ai` (Day 1) | `trustyai-config` (Day 2, this WP) |
|---|---|---|
| Change | `spec.components.trustyai.mcpGuardrailsMode: false -> true` in `gitops/charts/openshift-ai/values.yaml` | New RAGAS/Garak Job/CronJob templates and `values.yaml` entries (images, smoke-test config) |
| Scope | Single flag flip, live-verified like ADR-0108 verified `LMEvalJob` | Standalone smoke-test content only - no reference to Agent Runtime, RAG Service or MCP Gateway |

## Steps

### Step 1 - flip `mcpGuardrailsMode`

- `gitops/charts/openshift-ai/values.yaml`: `mcpGuardrailsMode: false` -> `true` under
  `spec.components.trustyai`.
- Live-verify the same way ADR-0108 verified `LMEvalJob`: a real reconciliation on this cluster, not
  just a green ArgoCD sync. Budget time for upstream operator quirks - ADR-0534's Operational
  considerations flags four already-documented 3.5.0-ea.2 bugs in this same operand.
- Re-run WP-107's LMEvalJob regression check to confirm the flip does not disturb the existing
  benchmarking path.
- Record the DSC's `trustyai` condition before and after the flip here (operator step).

### Step 2 - RAGAS as a generic evaluation framework

- Add a RAGAS Job/CronJob template to `gitops/charts/trustyai-config/templates/`, configured
  against a small fixed reference dataset/model pair (not a Zuno agent's live RAG output yet) -
  purely to prove the framework runs and produces a metrics report on this cluster's TrustyAI
  operand.
- `gitops/charts/trustyai-config/values.yaml`: image, resources, and reference-dataset config for
  the RAGAS smoke test.

### Step 3 - Garak as a generic evaluation framework

- Same pattern as Step 2, for Garak: a smoke-test scan against a reference model (not yet a Zuno
  agent's live model traffic), proving the scanner runs and produces a report.

### Step 4 - extend Day 2/Day 3 checks

- `ansible/roles/trustyai_config/tasks/precheck.yml` (from WP-107): extend to also assert the RAGAS
  and Garak smoke-test Jobs reach `Complete`, alongside the existing LMEvalJob health check - same
  file, same reuse-over-reinvention principle ADR-0534 asks for.

## What NOT to touch

- Do not add any hook into `agent-runtime`, `rag`, or `mcp-gateway` - that is WP-109's scope
  entirely. This WP's RAGAS/Garak content must be runnable and meaningful with zero Zuno agent
  traffic.
- Do not decide or implement blocking enforcement - `mcpGuardrailsMode: true` only enables the
  capability at the operand level; nothing in this WP calls it on real requests, so "observe vs
  block" does not yet apply here (it is WP-109's concern).

## Verification checklist (operator step - ask before running)

- `oc get datasciencecluster zuno-dsc -o jsonpath='{.status.conditions}'` shows the `trustyai`
  component healthy after the `mcpGuardrailsMode` flip.
- Existing LMEvalJob regression check still passes post-flip.
- A RAGAS smoke-test Job completes and produces a metrics report artifact.
- A Garak smoke-test Job completes and produces a scan report artifact.
- `make d2 install trustyai-config` and `make d3 check trustyai-config` both pass with the new
  content.
- `python3 platform/docs/check_docs.py` passes.
- Commit, push, and record live results above before marking this WP `Done`.

## Risks and known unknowns

1. **`mcpGuardrailsMode` flip may resurface or interact with the four documented upstream operator
   bugs** noted in ADR-0534 - test in isolation from RAGAS/Garak first if the flip alone causes
   instability, to keep the failure surface narrow.
2. **RAGAS/Garak images/versions compatible with this cluster's OpenShift AI 3.5.0-ea.2 release
   train are unverified** - confirm compatible versions exist before committing to specific image
   tags; if not yet published for this train, record the gap here rather than guessing.
3. **Resource footprint** - both frameworks may require GPU or significant CPU/memory; size the
   smoke-test Jobs conservatively and confirm against this cluster's known GPU/node constraints
   (see `docs/adr/0537-*.md` and related HardwareProfile work, WP-106).

## Status updates (once live-verified)

- This WP's own `State` moves to `Done` once Steps 1-4 are live-verified and the checklist above
  passes. ADR-0534 stays `Accepted`.
- **2026-09-02 - Done, with the brief's central premise refuted by its own Step 1.** Commits:
  `fc7b9dd1` (the flip - which ArgoCD's `ignoreDifferences` silently dropped), `806391b0` (the
  same-hour revert plus the in-place ADR-0534 Phase 2 amendment, after the live `oc patch` proved
  the flag strips the operator down to NEMO_GUARDRAILS-only and kills the LMEvalJob controller -
  see Live findings #1), `9c99c3a8` (the actual deliverables: Garak smoke Job on the
  operand-shipped image, `GuardrailsOrchestrator` with built-in detectors, day2/day3 precheck
  coverage), `a84ae6af` (closure). Verified live: `mcpGuardrailsMode` back at `false` with the
  full five-service operator, Garak smoke `succeeded=1`, the built-in detector answering on
  `/api/v1/text/contents`, and the LM-Eval path re-proven unbroken after the revert. RAGAS moved
  to WP-109 by decision (Live findings #3), not omission.
