# ADR-0596: Let experience clients pick a declared code model, routed to Codestral first

- **Status:** Implemented (2026-11-05, WP-194: Zuno Code served by Codestral from Open WebUI and OpenClaw on demo333, Zuno stays local)
- **Target:** v0.13
- **Date:** 2026-11-04
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0594](0594-give-the-three-experiences-the-same-mcp-tools-behind-signed-classification-markers.md) (unchanged, takes precedence), [ADR-0592](0592-declare-experience-clients-in-the-agents-release-apart-from-agents.md) (amended in part), [ADR-0588](0588-serve-a-general-purpose-chat-experience-with-open-webui.md) (amended in part: one model), [ADR-0587](0587-admit-additional-user-experiences-over-the-one-governed-backend.md), [ADR-0581](0581-derive-stack-configuration-from-the-admitted-corp-bundle.md), [ADR-0417](0417-consume-codestral-via-mistral-api.md), [ADR-0591](0591-route-only-to-ready-local-models-and-fail-fast-on-stalled-candidates.md), [ADR-0593](0593-key-the-per-user-quota-and-telemetry-by-persona-across-experiences.md), [ADR-0020](0020-support-both-local-and-external-llm-providers.md), [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)

## Context

On 2026-11-04 the same question, "write Python code that checks the format of an email address", was put to Open WebUI
and OpenClaw by sale-01, consultant-01 and consultant-02. Every call went to the local `qwen3.6-27b-instruct`. The user
asked why the ai-gateway did not see a code question and use Codestral, with the local model as fallback.

The ai-gateway chose qwen by design:

- It never reads the question to route. It routes on the classification, then on a per-(agent, task) preference from
  the routing policy generated out of the agents release (ADR-0581). Only `arkos` and `tekos` declare `write-code`
  with `mistral-codestral` first (ADR-0417).
- Open WebUI sends `X-Zuno-Agent: open-webui` and `X-Zuno-Task: chat`; OpenClaw sends `X-Zuno-Agent: openclaw` and
  no task on its model connection. No preference exists for either, so the candidates follow the routing table order,
  local models first. `local-maas` (qwen) answered, so nothing else was tried.
- WP-193 made the ai-gateway list `auto` alone ("Zuno") to experience clients. The `model` field is ignored, so a user
  has no way to ask for a code model.
- The generator (`platform/okf/generate_stack_config.py`) reads `agents/` only. The experience clients' tasks
  (ADR-0592) feed the mcp-gateway tool policy, never the model routing.

Measured on demo333 (Tempo, `model_call` spans): Open WebUI used 1,075 input and 3,641 output tokens in 2 min 48 s.
OpenClaw with consultant-02 made 8 calls (160,000 input tokens) in 5 min 10 s. From its second call on, OpenClaw was at
C2 and local-only: its own `exec`/`write` tool results carry no signed marker (ADR-0594 decision 3).

The key for `mistral-codestral` is provisioned on demo333 (`llm-provider-mistral-codestral`, `SecretSynced`). No
experience-client call has used it yet.

## Decision

**An experience client may offer a second model, "Zuno Code". The ai-gateway maps it to the client's declared task
`code`, whose routing puts Codestral first and the local models after it. The classification and ADR-0594 still decide
whether a SaaS model is allowed at all.**

1. **A declared model, mapped to a declared task.** For an experience client (the `MARKER_FAIL_CLOSED_CLIENTS` list),
   `GET /v1/models` returns two entries: `auto` ("Zuno") and `zuno-code` ("Zuno Code"). On `POST /v1/chat/completions`
   from such a client, `model: zuno-code` sets the task to `code`, in place of the `X-Zuno-Task` header. Any other
   `model` value keeps today's behaviour. The mapping is a closed table in the ai-gateway's configuration
   (`MODEL_TASK_ALIASES`, default `zuno-code=code`). It never names a provider: the model name only selects a task the
   client declares, and the routing policy decides the provider. Other callers (UnifAI and the platform clients) are
   unchanged.
2. **The task is declared in the agents release.** `open-webui` and `openclaw` each declare a task `code` with
   `zuno.models.preferred: [code]` and no tools of their own. Their MCP connection stays on the `chat` task, so the
   tool surface does not change. The generator reads the experience clients' tasks for the model routing only, with
   the same rules as for the agents (ADR-0581 steps 1 to 4). The resulting entry puts `mistral-codestral` first and
   leaves the corp order after it, local models first. It is not `strict`.
3. **The fallback is the routing table's.** If Codestral fails (key refused, 5xx, timeout, circuit breaker open,
   ADR-0591), the next candidate answers: `local-maas`, then `local`, then the rest in table order. The user gets an
   answer from qwen and the `model_call` span records the failed and the serving provider.
4. **The classification wins.** Codestral is eligible at C1 and C2 only. ADR-0594 is not changed: for an experience
   client, an unmarked tool result, or any call at C2 or above, makes the call local-only. A "Zuno Code" turn that uses
   a tool, and every OpenClaw turn after an `exec`, is answered locally. "Zuno Code" goes to Codestral only for a
   tool-free conversation at C1.
5. **Visible and counted.** The `model_call` span gains `zuno.task`. The tokens count against the persona's budget like
   any other call (ADR-0593). The Open WebUI banner and the demo script say that "Zuno Code" may send the conversation
   to Mistral, and that tool turns stay on local models.

> **Extension (2026-11-05, ADR-0599):** Dify is a third experience client under this decision. It is in
> `MARKER_FAIL_CLOSED_CLIENTS`, so `model: zuno-code` maps to its task `code`, and agents release v0.12.0 declares
> `dify` with tasks `chat` and `code` (`zuno.models.preferred: [code]`, no tools). On demo333, the ai-gateway
> reloaded the routing at 11:34:30Z. From 11:55Z, Dify's `code` calls were served by `mistral-codestral` (C1, 0.36 to
> 0.84 s) and its `chat` calls by `local-maas`. See the
> [WP-194 evidence](../roadmap/evidence/wp-194-zuno-code-live-proof.md#addendum-dify-agents-release-v0120).

## Alternatives considered

- **Codestral first for all of an experience client's traffic:** one routing entry, no ai-gateway code. Every question,
  including the non-code ones, would leave the cluster whenever it is C1, which inverts the local-first rule of ADR-0020
  for the whole client.
- **Detect code questions in the ai-gateway:** no user action needed. A classifier would add latency to every call, it
  would misread mixed questions, and it would move data to a SaaS provider on a guess. Routing only widens on an
  explicit declaration.
- **Let the user pick any model again (before WP-193):** a provider-level menu would bypass the routing policy, which is
  what WP-193 removed.
- **Per-model headers in the clients:** Open WebUI's headers are set per connection, not per model, and OpenClaw's per
  credential. Two connections to the same gateway would duplicate the configuration and the token handling.

## Consequences

- A user can ask for code help from Codestral in Open WebUI and in OpenClaw, and still gets an answer from qwen when
  Codestral is unavailable.
- C1 conversation content leaves the cluster when "Zuno Code" is picked. ADR-0021 allows that at C1, and the user makes
  the choice.
- ADR-0588 and WP-193 ("one model, Zuno") are amended in part: two models, both governed by the ai-gateway.
- ADR-0592 is amended in part: an experience client's task may declare `zuno.models`, and the generator reads it for
  the model routing. The agents repository's client checks accept a task without tools.
- The ai-gateway's rule "routing is classification-driven, never model-name-driven" becomes "a declared model name may
  select a declared task; the provider is still chosen by the classification and the routing policy".
- OpenClaw gains little: most of its code turns run tools, so they stay local. This is the intended effect of ADR-0594
  and is not changed here.
