# WP-108: TrustyAI generic RAGAS/Garak enablement and mcpGuardrailsMode flip

- **State:** Not started (2026-09-02)
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
