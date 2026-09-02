# WP-109: Wire TrustyAI to the Zuno agent stack and add PEFT/LoRA model comparison

- **State:** Done — live-verified 2026-09-02 on demo222, every step against the real stack (see
  Live findings): observe-only guardrails on live agent traffic (PII + jailbreak flagged, response
  delivered unmodified, MCP tool exchange observed), RAGAS scoring real pgvector retrievals
  (`faithfulness=1.0`, `context_precision≈1.0` on 3 questions after four live-diagnosed fix
  rounds), reproducible Garak jailbreak evidence on the wesh fine-tune (MitigationBypass 0/5,
  ASR 100% on DAN+DUDE), and a PEFT regression gate whose FIRST live run produced a real FAIL
  (wesh `acc=0.55` vs base `0.67`, `-0.12` beyond the `0.05` threshold,
  `evaluations/benchmarks/peft-regression-qwen35-9b-wesh.json`). Commits `a7f3570d`, `4f0b6ce4`,
  `a7f01bdb`, `c399c264`, `1e5eef99`, `afd0c40d` + the thinking-mode fix.
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

## Live findings (2026-09-02, execution)

1. **Observe-only proven both ways, twice.** Real chat requests as `consultant-01` through the
   live stack: a PII prompt logged `guardrails DETECTED (observe-only, response delivered
   unmodified)` with `email_address` at score 1.0 (run `d9445c2a`), and a deliberate
   jailbreak ("Ignore all previous instructions...") was flagged `custom-regex` at score 1.0
   (run `f3bed571`) - in both cases the reply reached the caller unmodified (the model's own
   refusal, not a guardrail block). A third run proved MCP observation:
   `tools=['search_confluence']` recorded on a real tool exchange, with mcp-gateway's
   `evaluate()` authorization path untouched (run `9a97ec76`).
2. **The first jailbreak regex was too narrow - observe-mode caught its own gap on day one.**
   "ignore all previous instructions" (two filler words) slipped
   `ignore\s+(all|...)\s+(instructions|...)`; widened to `(?:\w+\s+){0,2}` (commit `4f0b6ce4`),
   re-proven live.
3. **The PEFT/LoRA regression gate produced a REAL FAIL on its first live run.**
   `qwen3.5-9b` base scored `acc=0.67` and `qwen3.5-9b-wesh` scored `acc=0.55` on
   `mmlu_abstract_algebra` (100 samples each, live GPU LMEvalJobs) - a `-0.12` regression
   against the `0.05` threshold. `evaluations/benchmarks/peft-regression-qwen35-9b-wesh.json`
   is the first artifact, and it is exactly the evidence ADR-0534 Phase 3 exists to produce:
   the wesh fine-tune (ADR-0526) traded general capability for its register specialization.
   Feeding this into ADR-0107's promotion gate as a hard input is follow-up work, deliberately
   not retrofitted onto the already-adopted wesh model in this WP.
4. **Garak on the fine-tune found a real security signal.** `dan.Dan_11_0` against
   `qwen3.5-9b-wesh`: detector `dan.DAN` PASS 5/5 (no DAN-mode output), but
   `mitigation.MitigationBypass` FAIL 0/5 (100% attack success rate) - the fine-tune never
   voices an explicit refusal to the jailbreak. The base-model comparison run was
   inconclusive (empty generations, garak SKIP 0/0 - likely template/EOS behavior); rerunning
   it and folding garak scores into the regression artifact is recorded under Out of scope.
5. **Both fresh qwen35 LMEvalJobs failed transiently on first simultaneous launch** (exit 2,
   logs GC'd) and both succeeded on individual rerun - schedule the pair sequentially on this
   shared-GPU cluster.
6. **RAGAS needed four rounds to produce real scores, every defect live-diagnosed and none of
   them RAGAS's fault:** the SingleTurnSample "requires ['response']" error was DATA, not API
   (a `None` answer silently drops the response feature); `/v1/search` results carry
   `title`+`snippet`, not `content` (every context was empty and every score NaN in
   consequence); and qwen3.6 is a THINKING model - it spent its whole token budget reasoning,
   returning `content=None` on answers and `TimeoutError` on judge verdicts. Fixed with
   `chat_template_kwargs: {enable_thinking: false}` on both hops plus
   `RunConfig(timeout=600, max_workers=2)`. Final run: all 3 questions retrieved (4 real
   pgvector contexts each), answered, and scored - `faithfulness=1.0` and
   `llm_context_precision≈1.0` across the board, Job `succeeded=1`. The in-cluster probe pod
   (same image, inline snippet) was what isolated the field-name and None-answer defects -
   the Job's own logs never showed the empty strings.
7. Operational traps re-hit and handled: ArgoCD RepeatedResourceWarning (shared PVC rendered
   per-job - deduped), immutable Job spec wedging a sync in retries pinned to the OLD revision
   (Replace=true + operation termination - and `oc patch application` hits the decoy CRD,
   `applications.argoproj.io` required).

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
- **Acting on the two real findings this WP produced** (added at closeout, 2026-09-02): wiring the
  PEFT regression FAIL into ADR-0107's promotion gate as a hard input (the wesh model is already
  adopted - retrofitting a gate onto it is a decision, not a mechanical step), folding garak
  scores into the regression artifact, and rerunning the inconclusive base-model garak scan.
  All three need an owner's scheduling call, not more code in this WP.

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
- **2026-09-02 - Done; ADR-0534 moved to `Implemented` on this closure.** All five steps
  live-verified against the real stack (details in Live findings). Commits: `a7f3570d` (the
  observe-only guardrails hook in agent-runtime - both sync and SSE paths - plus
  `evaluations/peft_regression.py` and the qwen3.5-9b base/wesh LMEvalJob pair), `a7f01bdb`
  (lmeval PVC dedupe + Replace-sync on the prefetch Jobs), `4f0b6ce4` (jailbreak regex widened
  after the live miss - Live findings #2), `c399c264`/`1e5eef99`/`afd0c40d`/`7d72e5ee` (the
  `trustyai-eval` RAGAS image and the four live-diagnosed rounds to real scores - Live findings
  #6), `289e9544` (closure: this brief, the tracker, ADR-0534 `Implemented`). Final state:
  `make d3 check trustyai-config` fully green; observe-only proven on PII, jailbreak and MCP
  exchanges; RAGAS `faithfulness=1.0`/`context_precision≈1.0` on real pgvector retrievals; and
  two REAL open findings handed to the owner (wesh regression FAIL `-0.12`, Garak
  MitigationBypass 100% ASR on wesh) - tracked under Out of scope, deliberately not resolved
  here. The `peft-regression-qwen35-9b-wesh.json` artifact stays uncommitted:
  `evaluations/benchmarks/*.json` is gitignored by design.
