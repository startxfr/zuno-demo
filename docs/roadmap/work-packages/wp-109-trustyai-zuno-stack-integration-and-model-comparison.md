# WP-109: Wire TrustyAI to the Zuno agent stack and add PEFT/LoRA model comparison

- **State:** Not started (2026-09-02)
- **ADRs:** ADR-0534 (Accepted, Phase 2 Zuno-specific wiring + Phase 3 PEFT/LoRA comparison, merged
  into a single WP by decision - see Migration/evolution in the ADR)
- **Depends on:** WP-108 (Done - `mcpGuardrailsMode: true` live, RAGAS/Garak proven as generic
  frameworks); `agent-runtime`, `rag`, `mcp` (all Implemented)
- **Related:** ADR-0107/WP-10 (the model quality gate this WP's PEFT/LoRA comparison extends),
  ADR-0010/ADR-0011 (the MCP Gateway/tool-authorization boundary this WP's guardrails sit alongside,
  never inside)

## Goal

Hook TrustyAI in **front of Agent Runtime** so it can evaluate the full converged agent exchange -
retrieved RAG context, MCP tool use, and the final response - for RAG quality (RAGAS), response
quality, jailbreak/prompt-injection attempts and input/output filtering (Garak plus TrustyAI's own
guardrail detectors), starting in **observe/log-only mode**: evaluations run and are recorded, but
no request is blocked on their result. Separately, extend the same evaluation chain to Zuno's
PEFT/LoRA-customized models, comparing a fine-tuned candidate against its base model to catch
regressions before adoption, feeding ADR-0107/WP-10's model quality gate.

These two pieces are merged into one WP (rather than a separate Phase-3 WP, as ADR-0534 originally
suggested) because both extend the same TrustyAI evaluation chain onto Zuno-specific content -
Zuno's live agent traffic in one case, Zuno's fine-tuned models in the other - and share the same
`trustyai-config` component and precheck machinery.

## Why observe-only first

Guardrail evaluation on live agent traffic is new, untested behaviour. Blocking a real user
request on an unproven evaluator risks turning a false positive into a platform outage. This WP
therefore proves the wiring and collects evidence; a later, separate decision (its own WP) moves
specific guardrail checks from observe to block once that evidence supports a threshold. This
mirrors WP-085's own caution around Lightspeed's MaaS credential path - verify live before
committing to an irreversible-feeling default.

## Component and file layout

Builds on `trustyai-config` (WP-107 scaffold, WP-108 generic frameworks) - no new component.

| Piece | Where |
|---|---|
| Agent Runtime observation hook | `components/agent-runtime` - a call (or sidecar/middleware) at the boundary already described in ADR-0534's Context, sending the converged exchange (RAG context, MCP tool calls, final response) to TrustyAI for evaluation, and recording the result (logs/metrics) without altering the response |
| RAG quality evaluation | RAGAS invocation against the real `rag` service's retrieval output, replacing WP-108's fixed reference dataset for this specific check |
| Jailbreak / prompt-injection detection | Garak (or TrustyAI's own guardrail detectors) against sampled or full real agent traffic, replacing WP-108's reference-model smoke test for this specific check |
| MCP guardrails | Evaluation alongside (never inside) `components/mcp-gateway`'s existing `app/policy.py` authorization path (ADR-0010/ADR-0011) - guardrails add an observation signal, they do not replace or duplicate tool authorization |
| PEFT/LoRA comparison pipeline | New Job/pipeline in `trustyai-config` (or `evaluations/`, matching the existing `evaluations/benchmark.py` pattern from ADR-0108) running baseline vs candidate through LM-Eval + RAGAS + Garak and producing a pass/fail regression report |

## Steps

### Step 1 - Agent Runtime observation hook (observe-only)

- Add the call from `components/agent-runtime` to TrustyAI's evaluation surface, carrying the
  converged exchange. Emit results as logs/metrics only - no response mutation, no request
  rejection, regardless of the evaluation outcome. Make this explicit in code (a comment or a
  clearly-named no-op branch) so a future reader does not assume enforcement is live.
- Confirm no latency-sensitive path is blocked waiting on the evaluation call (fire-and-forget or
  async, not a synchronous gate on the response).

### Step 2 - RAG quality (RAGAS) on real retrieval

- Point RAGAS at the real `rag` service's retrieval output for a sample of live or replayed agent
  queries, replacing WP-108's fixed reference dataset for this specific evaluation.
- Produce a quality report per evaluated exchange, stored/logged for later threshold-setting work
  (out of scope here).

### Step 3 - jailbreak / prompt-injection detection on real traffic

- Wire Garak (or TrustyAI's own guardrail detectors, if better suited to live traffic than a batch
  scanner) against sampled or full real agent exchanges.
- Same observe-only contract as Step 1: flag, log, never block yet.

### Step 4 - MCP guardrails alongside the existing MCP Gateway boundary

- With `mcpGuardrailsMode: true` (WP-108) and the Agent Runtime hook in place (Step 1), confirm
  guardrail evaluation runs on MCP tool exchanges without touching `app/policy.py`'s existing
  `evaluate()`/`_evaluate_tool_policy()` authorization path (ADR-0010/ADR-0011) - two independent
  layers, as ADR-0534's Decision explicitly requires ("alongside it, never inside it").

### Step 5 - PEFT/LoRA baseline-vs-candidate comparison pipeline

- Build a comparison pipeline (reusing LM-Eval, RAGAS, Garak - the same three frameworks, not
  Zuno-specific reimplementations, per ADR-0534's stated preference) that runs a candidate
  fine-tuned model and its base model through the same evaluation suite and produces a single
  regression report: expected task-quality gain, plus regression checks on general response
  quality, RAG behaviour, tool/MCP usage capability, and security/jailbreak resistance.
- Feed this report into ADR-0107/WP-10's existing model quality gate as an additional input,
  without changing that gate's existing pass/fail mechanics for non-customized models.

## What NOT to touch

- Do not flip any guardrail check from observe to block - that is a later, separate decision and
  WP, made only after this WP's observation evidence exists.
- Do not move RAG retrieval or MCP tool invocation orchestration out of Agent Runtime into TrustyAI
  or the AI/Inference Gateway (ADR-0534 Non-goals).
- Do not modify `app/policy.py`'s existing `evaluate()` authorization logic - guardrails are an
  additive observation layer only.

## Verification checklist (operator step - ask before running)

- A real agent request through the live stack produces an observable TrustyAI evaluation record
  (log/metric) for RAG quality, jailbreak/prompt-injection and MCP guardrails - with the response
  delivered to the user unmodified (observe-only proven, not assumed).
- A deliberately crafted jailbreak/prompt-injection attempt is flagged in TrustyAI's evaluation
  output but still reaches the model/response path unblocked (confirms observe-only, not silent
  failure to detect).
- A PEFT/LoRA candidate model run through the comparison pipeline produces a regression report
  showing pass/fail per capability (task quality, general quality, RAG behaviour, tool/MCP usage,
  security/jailbreak resistance) against its base model.
- `make d3 test platform` (or the relevant Day 3 test target) still passes with the new hooks in
  place - no regression to existing agent behaviour.
- `python3 platform/docs/check_docs.py` passes.
- Commit, push, and record live results above before marking this WP `Done`.

## Out of scope / deferred

- **Blocking guardrail enforcement.** Moving any check from observe to block is a separate,
  later decision (and likely its own small WP) once this WP's observation evidence supports setting
  thresholds without an unacceptable false-positive rate.
- **Concrete evaluation datasets, thresholds and pass/fail policies** beyond what this WP's smoke
  and comparison pipelines establish - left to later ADRs/WPs per ADR-0534's Migration/evolution
  clause.

## Risks and known unknowns

1. **Where exactly the Agent Runtime hook lives (in-process call vs. sidecar) is undetermined** -
   decide based on `components/agent-runtime`'s existing structure and latency budget; record the
   choice and why here once made.
2. **Sampling vs. full-traffic evaluation** for Garak/jailbreak detection may be a cost/latency
   trade-off - start with sampling if full-traffic evaluation proves too expensive, and record the
   sampling rate chosen.
3. **PEFT/LoRA comparison pipeline's runtime** could be significant (multiple evaluation frameworks
   against two models) - confirm it fits within existing CI/Job time budgets or document why it
   runs out-of-band from any promotion gate's critical path.

## Status updates (once live-verified)

- This WP's own `State` moves to `Done` once Steps 1-5 are live-verified and the checklist above
  passes, with the observe-only contract explicitly proven (not assumed) for at least one real
  jailbreak/prompt-injection attempt. ADR-0534 stays `Accepted`.
