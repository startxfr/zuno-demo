# ai-gateway

Shared AI Inference Gateway (ADR-0009): resolves classification-eligible
providers (ADR-0021), tries them in fallback order (ADR-0020), and exposes
an OpenAI-compatible API - the single place inference routing/fallback
logic lives, kept separate from `components/agent-runtime`'s orchestration
(state, LangGraph workflow, tool/RAG invocation), per ADR-0009's decision.

Implementation: FastAPI (Python 3.11), stateless, no database. Deployed by
`ansible/roles/llm` via `gitops/apps/ai-gateway/application-d1.yaml` ->
`gitops/charts/ai-gateway` into the shared `zuno-ai-run` namespace.

## Why this exists as a separate service

Before this, routing/fallback/classification-eligibility lived inside
`components/agent-runtime`'s `ModelRouter`, which is what ADR-0009 was
tracked as "Accepted, not Implemented" for. Extracting it here means:

- `agent-runtime` no longer holds any provider API key or the routing
  config - it only knows this gateway's URL (`AI_GATEWAY_URL`).
- Routing/fallback/classification policy changes (which provider is
  eligible for which classification, fallback order, model names) are a
  redeploy of *this* service, not `agent-runtime`.
- A future second agent can reuse this gateway without re-implementing
  provider fallback.

## HTTP API contract

### `POST /v1/chat/completions`

OpenAI-compatible on the wire, with two Zuno-specific headers and one
Zuno-specific response field:

- **Auth:** `Authorization: Bearer <keycloak-jwt>` (required - validated
  against the realm's JWKS; this gateway does not do group-based
  authorization, only authenticated-caller verification).
- **Header:** `X-Zuno-Data-Classification: C1|C2|C3` (optional, default
  `C1`) - the primary input that selects the provider/fallback chain
  (ADR-0021). **`model` in the request body is accepted for wire-format
  compatibility but ignored for v0** - routing never looks at it; a future
  version could let a specific value pin/override the classification-driven
  decision (not built, tracked as follow-up, not a v0 requirement).
- **Header:** `X-Zuno-Local-Only: true|false` (optional, default `false`,
  ADR-0035) - a source-level restriction independent of classification:
  when `true`, candidates are filtered to local providers only regardless
  of what the declared classification's own SaaS-eligibility would
  otherwise permit. Set by the Agent Runtime when a contributing source
  this turn (e.g. Confluence, via the MCP Gateway's
  `external_model_policy.allow_context: false`) must never leave the
  cluster.
- **Body:**
  ```json
  {
    "model": "zuno-auto",
    "messages": [
      {"role": "system", "content": "..."},
      {"role": "user", "content": "..."}
    ],
    "stream": false
  }
  ```
- **Response `200` (non-streaming):**
  ```json
  {
    "id": "chatcmpl-...", "object": "chat.completion", "created": 1735689600,
    "model": "qwen2.5-7b-instruct",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "..."}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 128, "completion_tokens": 64, "total_tokens": 192},
    "zuno_provider": "local"
  }
  ```
  `zuno_provider` (not part of the OpenAI schema) names whichever provider
  in the fallback chain actually served the request.
- **Streaming (`"stream": true`):** standard OpenAI SSE chunk format
  (`data: {"id", "object": "chat.completion.chunk", "choices": [{"delta": {"content": "..."}, "finish_reason": null}]}\n\n`),
  terminated by `data: [DONE]\n\n`. **No provider-attribution header or
  field on the streaming path** - see "Streaming and fallback" below for
  why; check this gateway's OTel traces (`zuno.provider` span attribute)
  for provider attribution on a streaming call instead.
- **Response `422`:** the classification header is not `C1`/`C2`/`C3`, or
  no provider in `platform/ai-gateway/provider-routing.yaml` is eligible
  for the requested classification (ADR-0021 fail-closed).
- **Response `401`:** missing/invalid/expired JWT.
- **Response `502`:** every eligible provider failed (non-streaming path
  only - see below for the streaming failure shape).

### `GET /healthz` / `GET /readyz`

Liveness always `200`. Readiness returns `503` until
`provider-routing.yaml` has loaded successfully.

### `POST /admin/reload-routing`

Re-reads `provider-routing.yaml` from disk without a pod restart (mirrors
`mcp-gateway`'s `/admin/reload-policy`).

## Streaming and fallback

Non-streaming requests try every eligible provider in order until one
succeeds (`app/main.py:_invoke_with_fallback`, moved from the old
`ModelRouter.invoke_with_fallback`'s loop). Streaming requests fall back
the same way **only before the first token of a candidate has been sent**
(`app/main.py:_stream_completion`): once a provider has streamed any
content to the caller, a subsequent failure from that same provider ends
the response with a `finish_reason: "error"` chunk rather than silently
retrying - a client that already has partial output from provider A
cannot be seamlessly handed a fresh answer from provider B mid-response.
This is the fallback boundary the pre-refactor
`ModelRouter.streaming_model_for()` docstring described but never actually
wired up; it's implemented for real here.

## Why `agent-runtime`'s streaming needs no code changes

`components/agent-runtime`'s `reason_node` still just calls
`ChatOpenAI(...).ainvoke()`/relies on LangGraph's `astream_events` exactly
as before this split - only the `base_url` changed, from a specific
provider to this gateway. LangChain's OpenAI integration decides whether
to request `stream: true` from its target based on the surrounding
callback/streaming context, so the SSE-vs-plain-JSON choice at this
gateway's boundary is driven transparently by how `agent-runtime` is
invoking its client, not by anything `agent-runtime` has to configure
explicitly. This is the same implicit-streaming reliance the original
(pre-split) code already depended on - moving the HTTP destination doesn't
change that assumption, it was carried over as-is.

## Budgets and quotas: not implemented

ADR-0009's decision text names "budgets, quotas" alongside routing and
fallback. Nothing in this repository tracks spend or enforces a usage
ceiling anywhere - this gateway *measures* cost (`zuno.model_cost_usd`
OTel metric, `app/telemetry.py`) but does not enforce a limit. Confirmed
out of scope for this build: adding a real budget/quota mechanism (e.g. a
per-classification or per-provider request/token ceiling, likely enforced
here and backed by Vault or a ConfigMap for the limits) is future work.

## Configuration (env vars, no hardcoded secrets - ADR-0024)

| Var | Default | Purpose |
|---|---|---|
| `KEYCLOAK_ISSUER` | `https://keycloak-zuno.apps.mycluster.example.com/realms/zuno` | JWT issuer / JWKS base |
| `PROVIDER_ROUTING_PATH` | `/app/config/provider-routing.yaml` | routing config (ConfigMap-mounted, not baked into the image) |
| `LOCAL_MODEL_ENDPOINT` | `http://qwen25-7b-instruct-predictor.zuno-ai-run.svc:8080/v1` | local vLLM `InferenceService` OpenAI-compatible base URL |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` / `MISTRAL_API_KEY` | unset | sourced from the `ExternalSecret`s `ansible/roles/llm` registers against `zuno/providers/<name>` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://zuno-otel-collector-collector.zuno-telemetry.svc:4318` | where `app/telemetry.py` sends traces/metrics (ADR-0029) |

## Observability (ADR-0029)

`app/telemetry.py` wraps every provider attempt (streaming or not) in a
`model_call` span (provider, model, classification, latency, outcome) and,
when the model response exposes `usage_metadata`, records prompt/completion
token counts plus an estimated USD cost (`zuno.model_tokens` /
`zuno.model_cost_usd` metrics). Streaming calls only record latency/outcome
- LangChain does not reliably surface `usage_metadata` mid-stream across
all providers, and guessing would produce a misleading cost figure.

## Local development

```bash
cd components/ai-gateway
docker build -t zuno/ai-gateway:local .
docker run -p 8080:8080 \
  -e KEYCLOAK_ISSUER=https://keycloak-zuno.apps.mycluster.example.com/realms/zuno \
  -v $(pwd)/../../platform/ai-gateway/provider-routing.yaml:/app/config/provider-routing.yaml:ro \
  zuno/ai-gateway:local
```
