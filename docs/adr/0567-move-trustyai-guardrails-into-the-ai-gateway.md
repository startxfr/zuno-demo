# ADR-0567: Move TrustyAI guardrails into the ai-gateway

- **Status:** Partially implemented
- **Target:** v0.11
- **Date:** 2026-10-17
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0540](0540-express-guardrail-policy-as-nemo-rails-configuration.md) (express guardrail policy as NeMo rails configuration)
- **Related:** [ADR-0534](0534-integrate-trustyai-for-ai-evaluation-and-guardrails.md), [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md), [ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md), [ADR-0543](0543-propagate-a-per-run-id-across-every-service-span.md), [ADR-0560](0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md), [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md), [ADR-0565](0565-derive-data-classification-from-okf-and-only-allow-raising-it.md)

## Context

ADR-0534 placed TrustyAI guardrails "in front of Agent Runtime", explicitly
"alongside [the AI Gateway], never inside it", on the reasoning that Agent
Runtime is where RAG results, tool calls and the final response converge.
ADR-0540 then made the policy data (`gitops/charts/trustyai-config/files/nemo-rails/observe/config.yaml`,
rendered into ConfigMap `zuno-nemo-rails-observe` for `NemoGuardrails/zuno-guardrails`),
kept the rails model-free (empty `models:` block, pattern actions only), and
kept observation in three independent places: Colang flows that never `stop`,
a client that ignores the generated message, and a fire-and-forget call.

The client is `components/agent-runtime/app/clients/guardrails_client.py`.
`observe_exchange` runs after the reply is already delivered, sends the user
message and the final reply only (never the bearer token, project context,
document bodies or raw tool results), and selects a backend with
`GUARDRAILS_BACKEND`: `nemo` (live default since 2026-09-03,
`gitops/charts/agent-runtime/values.yaml` `guardrails.nemoUrl`) or `builtin`
(the `GuardrailsOrchestrator/zuno-guardrails-smoke` detector, whose entire
policy is the in-code `DETECTOR_PARAMS`, kept in step with the rails by the
`PolicyParityWithRails` test). Metrics `zuno.guardrails_evaluations` and
`zuno.guardrails_detections` come from `components/agent-runtime/app/telemetry.py`
and feed the `zuno-trustyai` dashboard.

ADR-0561 removes Agent Runtime. UnifAI has no guardrail hook and no OTel
metrics (ADR-0566 adds the latter). Re-implementing the observer inside the
UnifAI fork would make a Zuno-specific TrustyAI client part of the fork
delta ADR-0575 tries to keep small. The ai-gateway, which every Zuno agent
model call crosses (ADR-0560), is the remaining convergence point, and the
only one in the request path where a decision to block could ever be
enforced.

## Decision

**The guardrails client moves into the ai-gateway. Each chat completion is
evaluated there, in a mode - `observe` or `block` - declared per
classification level.**

1. **What is evaluated.** The input rail evaluates the last user message of
   the request; the output rail evaluates the completion. Retrieved documents
   and tool results that appear in the request's earlier messages are not sent
   by default, preserving the data-minimisation of the current client; an
   indirect-injection rail over that content is a separate, later policy
   addition.
2. **Mode per classification, declared as policy.** A policy file under
   `policies/guardrails/` declares, for each of C1/C2/C3, a `mode`
   (`observe` | `block`) and a `fail_mode` (`open` | `closed`), rendered into
   the gateway's configuration by the `llm` GitOps app like
   `provider-routing.yaml`. The classification used is the effective one after
   the ADR-0565 floor. **Every level ships as `observe`.** Moving a level to
   `block` is a reviewed policy edit, gated on the measurement ADR-0534 always
   required: a recorded false-positive rate on real traffic for that level.
3. **Observe mode keeps ADR-0540's three guarantees.** The rails still never
   `stop`, the generated message is still ignored, and the evaluation is still
   spawned after the response is returned or the stream closed, so it costs
   the caller nothing.
4. **Block mode is decided by the gateway, not by the rails.** The rails
   configuration stays observe-only; the gateway reads the activated-rails log
   and refuses when a detection class listed as blocking for that level fired.
   An input-rail block is evaluated synchronously before any provider is
   called and returns an OpenAI-style error (HTTP 400, `code:
   content_blocked`, naming the detection class, never the matched text). An
   output-rail block on a non-streaming call replaces the completion with the
   same error. On a streaming call the output rail stays observe-only even in
   block mode, because blocking it would require buffering the whole stream;
   a level that needs output blocking must say so and accept buffered
   delivery.
5. **Only the `nemo` backend moves.** The gateway client implements the
   NemoGuardrails request shape ADR-0540's evidence pinned (`config_id` and
   `options` nested under `guardrails`, `model` present), and nothing else.
   Under ADR-0540 Decision 4, the decision that retires
   `GuardrailsOrchestrator/zuno-guardrails-smoke` also deletes
   `DETECTOR_PARAMS` and `PolicyParityWithRails`: this is that decision, and
   all three go with Agent Runtime at WP-156.
6. **One observer at a time.** The gateway observer is enabled per cluster in
   the same change that empties the agent-runtime observer's URL (an empty
   endpoint already disables `observe_exchange`), so no exchange is counted
   twice. The metric names and detection-name label set are kept, emitted by
   the gateway's telemetry module with the `zuno.run_id` span attribute, so
   the `zuno-trustyai` dashboard needs no rename.

## Planned supersession

At cutover (WP-156):

- **ADR-0534, in part** - the placement clause ("hooking in front of Agent
  Runtime", "alongside it, never inside it") and the matching Non-goal. Its
  phases, its evaluation frameworks (LM-Eval, RAGAS, Garak) and its rule that
  blocking needs evidence first remain in force as its own decisions.
- **ADR-0540, in part** - Decision 3's statement that observation is
  observe-only "and stays that way" (replaced by clause 2's per-level mode)
  and Decision 4's backend selector in `agent-runtime` with its `builtin`
  fallback. Decisions 1 and 2 (policy as rendered rails data, rails without a
  model) remain in force.

## Consequences

Guardrails cover every caller of the gateway, not only agents: `mcp-gateway`,
which the gateway's NetworkPolicy admits as a caller, gains coverage it lacks
today.
Blocking becomes possible for the first time, and where it is possible -
before the provider call - is also the only place it is meaningful.

The unit of evaluation changes from one exchange to one model call. An agent
turn that makes several model calls produces several evaluations, so
`zuno.guardrails_evaluations` rises for the same traffic and the dashboard's
*Coverage* panel must be re-based on `zuno.run_id` to remain per-turn.
What ADR-0534 wanted from Agent Runtime's convergence - the final reply after
RAG and tools - is still seen: it is the completion of the turn's last model
call.

## Security considerations

In observe mode nothing reaches the observer that the gateway did not already
hold, and the observer is in-cluster (`zuno-ai-run`); the bearer token is
never sent. Clause 1 keeps document and tool content out by default.

Block mode with `fail_mode: closed` makes the NeMo server a hard dependency
of that level's chat path; ADR-0540 records that the server cannot be scaled
to zero, has a ~14GB image and must not schedule on control-plane nodes. A
level moving to block must state its fail mode deliberately; `open` keeps
chat available through an observer outage at the cost of unscreened traffic.

Error responses name the detection class only, so a blocked caller cannot use
them to probe the patterns.

## Operational considerations

The gateway's NetworkPolicy gains egress to `zuno-guardrails.zuno-ai-run.svc:80`.
The synchronous input rail adds one in-cluster call per model call in block
mode; its latency is measured on demo333 before any level is flipped (WP-153;
demo333 is powered off at the time of writing and the user must be asked to
power it on). ADR-0540's silent-failure traps carry over unchanged: a missing
ConfigMap or an unrecognised activated-rails payload yields zero detections
while healthy, so the precheck reads the ConfigMap's key set and the
*Observer unavailable (share)* panel stays. Every `oc` command passes
`--context` explicitly (ADR-0559).
