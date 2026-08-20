# ADR-0415: Consume stable-diffusion-xl via OVHcloud AI Endpoints

- **Status:** Proposed
- **Target:** v0.4
- **Date:** 2026-08-20
- **Decision owners:** Zuno Demo architecture team

## Context

None of arkos, advantage, cognos or comage can generate images today, and no
image-generation modality exists anywhere in the platform:
`platform/ai-gateway/provider-routing.yaml` only lists text-chat providers
(local qwen2.5-7b-instruct/gpt-oss-20b plus OpenAI/Gemini/Anthropic/Mistral
SaaS, ADR-0020/ADR-0021), and `components/ai-gateway/app/providers.py`'s
`chat_model_for` only ever builds a LangChain `BaseChatModel`. This decision
adds `stable-diffusion-xl`, consumed via OVHcloud AI Endpoints with
authenticated access, as the preferred model when a prompt or its context
requires image generation, for arkos, advantage, cognos and comage.

OVHcloud AI Endpoints exposes stable-diffusion-xl through two API shapes
(verified against the live catalog/getting-started pages, 2026-08-20):

- A raw endpoint (`POST .../api/text2image`, `prompt`/`negative_prompt` in,
  binary JPEG out).
- An OpenAI-compatible endpoint
  (`POST https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/images/generations`,
  `model`/`prompt`/`size` in, `data[0].b64_json` out).

Both require `Authorization: Bearer $OVH_AI_ENDPOINTS_ACCESS_TOKEN`, obtained
from a Public Cloud project with a payment method attached (AI Endpoints
Getting Started guide). Authenticated calls get 400 req/min per project per
model, versus 2 req/min anonymous.

Every existing SaaS provider in this repo (`openai`, `gemini`, `anthropic`,
`mistral`) is consumed through the `openai`/vendor SDK by
`components/ai-gateway`, the platform's sole model-consumption gateway
(ADR-0009). OVHcloud's OpenAI-compatible endpoint lets this decision follow
that same shape exactly, rather than introducing a bespoke HTTP client.

Two constraints specific to this addition, both surfaced by reading the
current agent-runtime implementation rather than assumed:

1. **Classification conflict.** Arkos and cognos are `C3`
   (`policies/model-routing/model-routing-policy.yaml`,
   `agents/{arkos,cognos}/agent.okf.md`'s `model.preferred_classification`):
   local-model-only, never leaves the cluster (ADR-0021, ADR-0035). OVHcloud
   is an external SaaS endpoint, so routing image-generation calls there
   conflicts with that guarantee for these two agents.
2. **History/compaction budget.** `components/agent-runtime/app/graph/
   history.py` caps each history entry at `HISTORY_ENTRY_MAX_CHARS` (4000)
   and estimates tokens with a char/4 heuristic for ADR-0215's budgeted
   compaction. A raw base64 image embedded in that text-based `history`/
   `summary` path would either be corrupted by truncation or wreck the
   token budget on the next turn.

## Decision

1. **Provider.** Register `stable-diffusion-xl` as a new, separate image
   provider (`kind: saas-image`) via OVHcloud's OpenAI-compatible endpoint,
   authenticated by a Vault-backed `ExternalSecret` (`providers/ovhcloud`,
   property `api_key`) following the exact pattern already used for
   `openai`/`gemini`/`anthropic`/`mistral` (ADR-0024). Kept in a sibling
   config (`platform/ai-gateway/image-provider-routing.yaml`) and gateway
   module rather than folded into the existing chat-only
   `provider-routing.yaml`/`RoutingTable`, since every part of that path is
   documented and typed around `BaseChatModel` text completion.
2. **Dispatch.** Image generation is an explicit tool
   (`generate_image`, capability `image.generation.create`), invoked by the
   calling agent's LLM when it decides an image is needed — not an
   automatic classifier reroute. It is bound to the reasoning model via
   LangChain tool-calling, resolved through the MCP Gateway's existing
   authorization intersection (ADR-0011) with an in-process handler
   (ADR-0116's `transport: in-process`, the same pattern as the `drive`/
   `web_search` handlers), never a new standalone MCP server. The tool's
   only input is the `prompt`/`negative_prompt` string text the LLM itself
   composes — never raw retrieved documents, citations or conversation
   history.
3. **Classification.** The `generate_image` tool call is always evaluated
   at a fixed `C2` ceiling, regardless of the calling agent's ambient
   classification. For arkos and cognos this is a narrow, explicit
   exception to their `C3`/local-only guarantee, scoped to this one call
   type only — every other call these two agents make stays `C3`/local-only,
   unchanged. See Accepted risks.
4. **Scope.** Available to arkos, advantage, cognos and comage. Cognos is
   forward-declared only (policy/task config updated, matching how its text
   model preference is already forward-declared despite being an inert
   placeholder) — no chart or deployment change for cognos.
5. **Persistence and display.** No new database or table: conversation
   turns already live entirely in `components/agent-runtime`'s LangGraph
   `AsyncPostgresSaver` checkpointer (ADR-0103). A new `generated_images`
   `AgentState` channel rides on that same store. Past-turn images are
   represented to the LLM in `history`/`summary` only as a short text
   placeholder (`[Generated image: <prompt>]`) — the base64 payload is
   never re-injected into a subsequent LLM call, addressing constraint 2
   above. The full payload is carried to the frontend as a sidecar `images`
   field on the chat response/SSE `done` event, mirroring the existing
   `citations` sidecar field, and rendered inline in the message bubble
   alongside the surrounding text.

## Alternatives considered

- **Automatic intent classification/routing** instead of an explicit tool —
  rejected: requires building a new modality classifier with no existing
  precedent in this repo, for a capability that fits naturally as a normal
  LLM-directed tool call.
- **Downgrade arkos/cognos from C3 to C2 entirely** to remove the
  classification conflict — rejected: broader than this decision needs;
  weakens their local-only guarantee for all traffic, not just image
  generation, contradicting the reason they were seeded C3 in the first
  place (sovereign-marked DAT/board workflows).
- **Skip arkos/cognos, wire OVHcloud only for advantage/comage** (already
  `C2`, already permitted to reach external SaaS) — rejected: the user's
  requirement is explicit that all four agents get preferred image
  generation; deferring two of them was not chosen.
- **A dedicated `mcp-image-gen` MCP server**, matching every other tool's
  `streamable-http` binding — rejected in favor of an in-process handler:
  one thin call to `components/ai-gateway`'s new endpoint does not justify
  a new deployable component, and ADR-0116's binding schema already
  supports in-process handlers for exactly this kind of lightweight case
  (`drive`, `web_search`, `email_report`).
- **Persist generated images to S3** (alongside `zuno-demo-rag-corpus`) and
  return a URL instead of inline base64 — not selected; the user asked for
  conversation-memory persistence with inline chat display, which the
  existing checkpointer already provides without new infrastructure.

## Accepted risks (and their remediations)

- **The C2 classification override for arkos/cognos's `generate_image` call
  narrows ADR-0021/ADR-0035's "C3 never leaves the cluster" guarantee.**
  Residual exposure: the prompt text the LLM composes for image generation
  could still inadvertently reflect derived C3 content, even though no raw
  context/citations/history are passed to the tool by construction.
  Remediation: none beyond the structural narrowing to a short prompt
  string described above — accepted as a deliberate, scoped trade-off for
  this one capability. If this proves insufficient, a follow-up ADR should
  add prompt-content screening before the call, not a wider classification
  change.
- **Real LLM-directed tool-calling has no precedent in agent-runtime.**
  Today's `tool_call_node` (`components/agent-runtime/app/graph/nodes.py`)
  calls exactly one task-configured `live_read_tool` deterministically,
  before reasoning. Binding `generate_image` on the reasoning model and
  adding a tool-execution branch to the graph shape(s) these four agents
  use (`plan_draft_write`, the `retrieve_reason_respond` family, ADR-0342)
  is new capability, not a config change. Remediation: implement and test
  narrowly against one agent (arkos) before extending to the other three.
- **OVHcloud rate limits (400 req/min per project per model, authenticated)
  are shared across all four agents from one Public Cloud project.** A
  demo burst across agents could hit the ceiling. Remediation: none planned
  initially — matches the size of this deployment; revisit (a support
  request for a higher limit, or per-agent throttling) if it recurs.
- **No automated upload/version-pinning exists for this model** — OVHcloud
  hosts and versions `stable-diffusion-xl` itself, unlike the
  manually-staged local weights in `s3://zuno-demo-rag-corpus/models/`.
  Remediation: none needed; this is inherent to consuming a managed SaaS
  endpoint rather than self-hosting.
- **Local vLLM tool-call parsing is unverified against a live cluster.**
  Arkos and cognos route their `generate_image`-deciding reasoning call
  (never the OVHcloud call itself) through local qwen2.5-7b-instruct/
  gpt-oss-20b per their normal C3/local-only chain, so those servers must
  actually parse `tool_calls` out of the model's own output -
  `gitops/charts/models/templates/servingruntime.yaml`/
  `llminferenceservice-gptoss.yaml` now pass `--enable-auto-tool-choice`
  and a best-guess `--tool-call-parser` (`hermes` for qwen, `openai` for
  gpt-oss), matching this same file's pre-existing `--lora-modules`
  "UNVERIFIED, confirm with `--help`" posture. Remediation: confirm the
  parser name against the pinned `image.vllm` build's `--help` output and
  a real tool-calling request before considering arkos/cognos's path
  proven; advantage/comage's SaaS fallback candidates (OpenAI/Anthropic)
  support tool-calling natively regardless.

## Related ADRs

- [ADR-0009](0009-separate-agent-runtime-from-ai-inference-gateway.md)
- [ADR-0010](0010-introduce-a-central-mcp-gateway.md)
- [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md)
- [ADR-0020](0020-support-both-local-and-external-llm-providers.md)
- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)
- [ADR-0024](0024-use-vault-for-application-secrets.md)
- [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md)
- [ADR-0045](0045-stream-responses-end-to-end-with-sse.md)
- [ADR-0116](0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md)
- [ADR-0215](0215-carry-conversation-history-into-agent-prompts-with-budgeted-compaction.md)

See [Standard clauses](README.md#standard-clauses) for Consequences, Security/Operational
considerations, Migration/evolution, Acceptance criteria and Review evidence.
