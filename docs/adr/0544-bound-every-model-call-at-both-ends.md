# ADR-0544: Bound every model call at both ends - a prompt-window clamp and a declarative max_tokens

- **Status:** Implemented
- **Target:** v0.4
- **Date:** 2026-09-03
- **Decision owners:** Zuno Demo architecture team

## Context

Formalizing the fleet's architectural roles (ADR-0518/ADR-0526/ADR-0531, and their 2026-09-03
correction notes) surfaced a real, unaddressed bug rather than a documentation one. `qwen3.5-9b`
(role `default`, `platform/ai-gateway/provider-routing.yaml`) is a structurally always-reachable
terminal fallback for essentially every `(agent, task)` chain since ADR-0531 decision 1 - it
either leads a chain or is appended as an unlisted survivor - and it serves
`--max-model-len=8192`, while the other three local chat models
(`qwen3.6-27b-instruct`/`gpt-oss-20b`/`qwen3.5-9b-wesh`) serve 32768. Nothing in
`components/agent-runtime` knew that: it assembles a chat prompt (system prompt + conversation
history + project context + RAG/live-read context) against a static per-agent budget
(`app/registry.py`'s `HISTORY_TOKEN_BUDGET`, 1800 by default, 6000 for Arkos) with no visibility
into which model will actually serve the turn - model selection happens entirely inside
`components/ai-gateway`, after the fully-assembled prompt has already been dispatched.

Measured live 2026-09-03 against Arkos's real corpus and the real running predictors
(`agents/arkos/agent.okf.md`): its two RAG-bearing tasks
(`draft-architecture-testimonial`/`workshop-presentation`) assemble `6000 (history) + ~420
(system prompt) + up to 1200 (project context) + 5 RAG chunks (~312 tokens median, ~449 p95 -
real rag-tech corpus stats)` = `~9,180-9,865` tokens against an 8192-token window, overflowing
before a single output token - on the exact fallback path the fleet-default guarantee makes
always reachable. `_build_context_block`'s RAG/live-read content carried no token budget at all
before this ADR; only history and project context did, each independently, against a constant
neither knew the selected model's real window.

Separately, nothing in the platform caps how long a model may generate for. `structure-demo`
(Arkos's `structure a demo` task) exposed this concretely: its preferred candidate,
`qwen3.6-27b-instruct`, measures ~18 tok/s live, a genuine load-independent speed limit - a
demo-narrative-length reply routinely ran past a minute of generation. `evaluations/arkos/
scenarios.yaml`'s own scenario 9 had already been raised from the handler's 30s default to 180s
the day before this ADR (`e138280e`, 2026-09-02, matching scenarios 7/10 and the real production
ceiling, `components/agent-bff/main.go`'s 180s streaming context deadline, in place since
2026-08-21) - so the eval-side symptom was already fixed, but nothing structural stopped a reply
from simply running long, and no per-task generation ceiling existed anywhere in the platform to
express one.

## Decision

1. **A new `max_model_len` field on every LOCAL `provider-routing.yaml` entry**, mirrored from
   `gitops/charts/models/values.yaml`'s own `maxModelLen` per served model and cross-checked
   against it by a new `platform/docs/check_docs.py` invariant (`model_context_windows`, the
   platform's 14th check) - the missing cross-reference that let the two files silently agree by
   accident is exactly what let this bug exist unnoticed. SaaS providers deliberately omit the
   field: their windows are never the binding constraint, and a value nothing in this repo can
   verify is the same class of drift the check exists to prevent. `-maas` and direct siblings of
   one served model must agree - they front the same runtime - and the check enforces that too.
2. **`components/agent-runtime/app/graph/prompt_budget.py` clamps the assembled prompt against
   the fleet's real narrowest reachable window - a new module, not a routing decision moved into
   agent-runtime.** It reads exactly one field, `max_model_len`, across `kind: local` providers
   in the same `provider-routing.yaml` ConfigMap ai-gateway already reads, and takes `min()` -
   never `eligible_for`/`prefer`/file order/anything routing-shaped. Building a second,
   independently-maintained routing implementation inside agent-runtime was rejected outright: it
   is exactly the drift class this repo spent 2026-09-03 finding and fixing instances of
   elsewhere (ADR-0518/ADR-0531's contradiction). A synchronous "ask ai-gateway which model first"
   handshake was considered and also rejected - model selection is not a discrete decision point
   on the gateway side today (it is entangled with the per-candidate try/fallback loop), and
   building one was judged disproportionate to the fix. The chosen mechanism is static and
   deliberately conservative: it clamps toward the fleet's worst case on every turn that would
   overflow it, whether or not the narrow model ends up serving that particular turn.
3. **The declared per-agent/task budget is never rewritten - only bypassed at assembly time, on
   a turn that actually needs it.** `allocate_prompt_budget` returns the caller's own budgets
   unchanged (`clamped=False`) whenever a turn already fits; Arkos's deliberately generous
   6000-token history budget stays meaningful on its 32768-token nominal path. Sacrifice order
   when it does not fit: project context first (floor 0 - static across the engagement, already
   framed as background per ADR-0527), then history (floor ~512, `build_history_messages`
   already guarantees at least one verbatim turn regardless), RAG/live context last (floor ~512
   - retrieved for THIS question, so it gives way last of the three). A still-too-long prompt
   after every floor is hit is sent anyway, logged, never rejected locally.
4. **Both real prompt-assembly sites are clamped, plus the single largest unbounded payload in
   the pipeline.** `app/graph/nodes.py`'s `reason_node`/`code_node` and `app/graph/arkos_nodes.py`'s
   `draft_node`/`code_node`/`demo_node` all thread the clamp; `arkos_nodes.py`'s `reflect_node` -
   which sends Arkos's entire drafted document body as the human message, unbounded before this
   ADR - is clamped too. Leaving a full document draft unbounded while clamping a 312-token RAG
   chunk would have been incoherent.
5. **`ai-gateway` gains a pre-flight skip using the same `max_model_len` field it already loads**,
   in both `_invoke_with_fallback` and `_stream_completion`: a candidate whose own window a
   char/4 estimate of the prompt clearly exceeds is skipped with an attributable log line, rather
   than dispatched to fail generically (today's `except Exception`, indistinguishable from a
   network blip). The last remaining candidate is never skipped - trying it and surfacing the
   real upstream error beats an estimate-based refusal that might be wrong. This is also the only
   protection a non-agent-runtime caller (Lightspeed) gets; `prompt_budget.py`'s clamp never runs
   for it.
6. **A new, general `zuno.max_tokens` OKF task property** (`platform/okf/schema/
   zuno-okf-task-v0.2.schema.json`, `[1, 8192]`), forwarded end to end as a new per-REQUEST
   `X-Zuno-Max-Tokens` header - `components/agent-runtime/app/clients/model_router.py` sends it
   conditionally (same convention as every other optional `X-Zuno-*` header), `app/main.py`
   parses it defensively (`_parse_max_tokens`: a malformed or out-of-range value is logged and
   ignored, never a 4xx - the same posture every header here already takes), and
   `app/providers.py` forwards it into every per-vendor factory, including the one real
   translation this needs (`max_output_tokens` on Gemini, `max_tokens` everywhere else) and the
   `via_maas` branch (`app/maas_adapter.py`) - load-bearing, since `structure-demo`'s own
   preferred candidate (`local-maas`) is `via_maas: true` and is built there, not by
   `app/providers.py`'s local branch.
7. **Threaded generically across every node, not wired for `structure-demo` alone.** The
   alternative - a task-specific special case - reproduces this repo's own known dead-field
   pattern (`zuno.quota_class` is declared in the schema and read by ai-gateway, but
   agent-runtime never actually sends the header for it). `structure-demo` is simply this
   mechanism's first real user: `max_tokens: 1536` (~85s at its measured ~18 tok/s, a 2x margin
   under the real 180s production ceiling), also feeding decision 3's clamp as the turn's output
   reserve so the model's context window is never sized as if the whole thing were free for
   input.
8. **`agent-runtime`'s own `provider-routing.yaml` mount is `optional: true`.** Unlike
   `ai-gateway`, which cannot route at all without this file, `prompt_budget.py` degrades to a
   conservative built-in constant (8192, the fleet's narrowest window today) when it is missing -
   this service must not gain a startup-ordering dependency on the `llm` Application for a
   feature that already has a safe default.

## Non-goals

A live handshake letting ai-gateway tell agent-runtime the precisely-selected model's window
before assembly (rejected in decision 2 - the static floor is deliberately conservative instead);
per-`(agent, task)` precision in the clamp floor, which would require agent-runtime to parse
`eligible_for`/`prefer` and become the second routing implementation decision 2 explicitly
avoids (`arkos/write-code`'s `strict: [mistral-codestral]` chain can never reach a local model at
all and is still clamped to the global floor - accepted, since that call carries no
history/RAG to begin with, so the floor never actually binds there); raising
`HISTORY_TOKEN_BUDGET_DEFAULT`/any per-agent budget - this ADR bounds the assembled prompt, it
does not change what any agent declares wanting.

## Operational considerations

- **The real cost of a static, conservative floor, stated plainly:** every turn that can reach a
  local model is clamped toward 8192, including turns the 27B/gpt-oss-20b/wesh actually end up
  serving. On Arkos's two RAG-bearing tasks that means project context sheds to 0 and history
  drops from 6000 to roughly 4500-5200 on the narrow-window path, while every RAG chunk is kept.
  This is the accepted price of adding no runtime handshake.
- **Reserving room for the reply changes which turns are exempt.** `structure-demo`/`write-code`
  (no RAG) assemble ~7,414 tokens - inside the raw 8192 window, but not inside the ceiling once
  an output reserve is held back (8192 minus a 1024-token default reserve, or `structure-demo`'s
  own declared 1536, leaves 7168/6656) - so even these two now shed a few hundred tokens of
  project context on the narrow-window path. Caught only by actually running the clamp against
  the measured numbers while building it, not by reasoning about the raw window alone -
  `tests/test_prompt_clamp.py` pins both figures as regression fixtures.
- **`policies/optimization/optimization-policy.yaml`'s tuner cannot touch any of this** - `prefer`
  and `max_tokens` are both outside its enumerated, pre-approved scope by construction (no code
  change was needed to keep it that way).

## Verification

- `platform/docs/check_docs.py` - 14 checks, PASS.
- `platform/okf/generate_authorization_matrix.py --check --all` - PASS (unchanged; this ADR adds
  no new provider or role).
- `components/agent-runtime`: `tests/test_prompt_clamp.py` (11/11) reproduces the measured
  overflow as a fixture and proves the fix against it, including an end-to-end run of the real
  `draft_node` against the real Arkos bundle; `tests/test_max_tokens.py` (6/6) proves the
  schema-to-header chain against the real `structure-demo` declaration. Full suite: 23/23
  standalone scripts green (these are not a pytest suite - see
  `components/agent-runtime/tests/`'s own convention).
- `components/ai-gateway`: `tests/test_max_tokens_passthrough.py` (16/16) covers header parsing
  and every per-vendor factory branch, including the load-bearing `via_maas` case. Full suite:
  148/148 (one pre-existing spy fixture in `tests/test_maas_adapter_guard.py` needed its
  signature widened for the new `max_tokens` keyword - a real, expected consequence of adding a
  parameter to `chat_model_for`, fixed alongside this ADR).
- `agents/arkos/tests/tasks/test_task_declarations.py` gains a non-vacuous assertion that
  `structure-demo`'s declared `max_tokens` is within the schema's bound.
- `helm lint`/`helm template` on `gitops/charts/agent-runtime` - clean; the new `provider-routing`
  volume renders with `optional: true` as designed.

## Migration / evolution

No infrastructure change beyond the `agent-runtime` chart's new optional ConfigMap mount (decision
8). Rollback is a pure code/config revert - no `LLMInferenceService`, quota, or MIG change is
touched.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered (beyond decision
2's own recorded rejections), Consequences, Security considerations, and Review evidence.

## Related ADRs

- [ADR-0518](0518-modernize-local-models-qwen36-chat-qwen3-embeddings-qwen35-training.md),
  [ADR-0526](0526-fine-tune-and-serve-a-french-urban-register-model-variant.md),
  [ADR-0531](0531-promote-qwen3-5-9b-as-the-fleet-wide-default-and-extend-ovhcloud-reasoning-access.md) -
  the fleet-role formalization whose live measurement surfaced this bug; this decision is
  downstream of theirs, not a correction to them.
- [ADR-0215](0215-carry-conversation-history-into-agent-prompts-with-budgeted-compaction.md) - the
  `history_token_budget`/`build_history_messages` mechanism decision 3's clamp wraps without
  changing.
- [ADR-0419](0419-split-model-preference-into-preferred-fallback-with-prompt-slot-overrides.md) -
  the `preferred:`/`fallback:` chain semantics decision 2 deliberately does not replicate.
- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md),
  [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md) - the
  eligibility/local-only filtering this ADR's clamp and pre-flight skip sit downstream of and
  never override.
- [ADR-0527](0527-introduce-the-project-as-the-sharing-and-context-boundary.md) - the project
  context framing ("background, not instructions") that makes it the first thing decision 3
  sheds.
