# ai-gateway

Shared AI Inference Gateway: resolves classification-eligible providers,
tries them in fallback order, and exposes an OpenAI-compatible API - the
single place inference routing/fallback logic lives, kept separate from
`components/agent-runtime`'s orchestration (state, LangGraph workflow,
tool/RAG invocation).

Implementation: FastAPI (Python 3.11), stateless, no database. Deployed by
`ansible/roles/llm` via `gitops/apps/ai-gateway/application-d1.yaml` ->
`gitops/charts/ai-gateway` into the shared `zuno-ai-run` namespace.

## Why this exists as a separate service

`agent-runtime` no longer holds any provider API key or the routing
config - it only knows this gateway's URL (`AI_GATEWAY_URL`).
Routing/fallback/classification policy changes (which provider is
eligible for which classification, fallback order, model names) are a
redeploy of *this* service, not `agent-runtime`.

## HTTP API contract

### `POST /v1/chat/completions`

OpenAI-compatible on the wire, with two Zuno-specific headers and one
Zuno-specific response field:

- **Auth:** `Authorization: Bearer <keycloak-jwt>` (required - validated
  against the realm's JWKS; this gateway does not do group-based
  authorization, only authenticated-caller verification).
- **Header:** `X-Zuno-Data-Classification: C1|C2|C3` (optional, default
  `C1`) - the primary input that selects the provider/fallback chain.
  **`model` in the request body is accepted for wire-format
  compatibility but ignored for v0** - routing never looks at it.
- **Header:** `X-Zuno-Local-Only: true|false` (optional, default `false`) -
  a source-level restriction independent of classification:
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
    "model": "qwen3.6-27b-instruct",
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
  for the requested classification (fail-closed).
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
succeeds (`app/main.py:_invoke_with_fallback`). Streaming requests fall
back the same way **only before the first token of a candidate has been
sent** (`app/main.py:_stream_completion`): once a provider has streamed
any content to the caller, a subsequent failure from that same provider
ends the response with a `finish_reason: "error"` chunk rather than
silently retrying.

## Why `agent-runtime`'s streaming needs no code changes

`components/agent-runtime`'s `reason_node` still just calls
`ChatOpenAI(...).ainvoke()` / relies on LangGraph's `astream_events` -
only the `base_url` changed, from a specific provider to this gateway.
LangChain's OpenAI integration decides whether to request `stream: true`
based on the surrounding callback/streaming context, so the
SSE-vs-plain-JSON choice at this gateway's boundary is driven
transparently by how `agent-runtime` invokes its client.

## Budgets and quotas: not implemented

Nothing in this repository tracks spend or enforces a usage ceiling
anywhere - this gateway *measures* cost (`zuno.model_cost_usd` OTel
metric, `app/telemetry.py`) but does not enforce a limit. A real
budget/quota mechanism (e.g. a per-classification or per-provider
request/token ceiling) is future work.

## Semantic caching

`app/semantic_cache.py` is an opt-in cache for non-streaming
`/v1/chat/completions` responses, stored in the existing platform Redis
(`gitops/charts/redis`, the same instance `components/agent-frontend`
already uses for sessions). Two gates, both must be true or nothing is
cached: the chart-level `semanticCache.enabled` switch (`SEMANTIC_CACHE_ENABLED`,
default off) and the specific model's `cache_enabled: true` entry in
`platform/ai-gateway/provider-routing.yaml` (no entry sets it yet).

The cache key binds to model identity, caller subject, effective
classification, `X-Zuno-Local-Only`, and task identity (`X-Zuno-Task`) -
change any one of these and it's a guaranteed miss, never a cross-boundary
hit. "Semantic" means the prompt is embedded (via the same shared
embedding `InferenceService` `components/rag-service` uses,
`EMBEDDING_SERVICE_URL`) and bucketed with a small, fixed set of random
hyperplanes (SimHash-style locality-sensitive hashing) rather than
matched on exact prompt text - cosine-similar prompts land in the same
bucket with high probability. Cache infrastructure failures (Redis or the
embedding service unreachable) fail open: the request proceeds uncached.
This is a latency/cost optimization, never a correctness or security
control - the routing/eligibility check in `app/routing.py` always runs
before any cache lookup regardless. Streaming responses are never cached.

Hit/miss/unavailable outcomes are recorded on the `zuno.semantic_cache_lookups`
metric and the request's own trace span (`app/telemetry.py:record_cache_outcome`).

## Configuration (env vars, no hardcoded secrets)

| Var | Default | Purpose |
|---|---|---|
| `KEYCLOAK_ISSUER` | `https://keycloak-zuno.apps.mycluster.example.com/realms/zuno` | JWT issuer / JWKS base |
| `PROVIDER_ROUTING_PATH` | `/app/config/provider-routing.yaml` | routing config (ConfigMap-mounted, not baked into the image) |
| `LOCAL_MODEL_ENDPOINT` | `https://qwen36-27b-instruct-kserve-workload-svc.zuno-ai-run.svc:8000/v1` | local vLLM `LLMInferenceService` OpenAI-compatible base URL |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` / `MISTRAL_API_KEY` | unset | sourced from the `ExternalSecret`s `ansible/roles/llm` registers against `zuno/providers/<name>` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://zuno-otel-collector-collector.zuno-monitoring.svc:4318` | where `app/telemetry.py` sends traces/metrics |
| `SEMANTIC_CACHE_ENABLED` | `false` | global cache switch (chart value `semanticCache.enabled`) |
| `SEMANTIC_CACHE_TTL_SECONDS` | `3600` | cache entry TTL |
| `EMBEDDING_SERVICE_URL` | `http://embeddings-predictor.zuno-ai-run.svc:8080/v1/embeddings` | shared embedding `InferenceService` the cache buckets prompts against |
| `REDIS_ADDR` / `REDIS_PASSWORD` | `zuno-redis-master.zuno-auth.svc.cluster.local:6379` / unset | shared platform Redis (cache backend) |

## Observability

`app/telemetry.py` wraps every provider attempt (streaming or not) in a
`model_call` span (provider, model, classification, latency, outcome),
unconditionally for every outcome. When the model response exposes
`usage_metadata`, it additionally records prompt/completion token counts
(`zuno.model_tokens`). Streaming calls accumulate their chunks
(`AIMessageChunk.__add__`) and read `usage_metadata` off the merged result,
same as the non-streaming path - `app/providers.py`'s `ChatOpenAI(...,
stream_usage=True)` is what makes the terminal chunk of an OpenAI/vLLM
stream carry it (VERIFIED live 2026-08-18: before this, since agent-runtime
always streams, `zuno.model_tokens`/`zuno.model_cost_usd` had zero series
regardless of real traffic). `gemini`/`anthropic`/`mistral` candidates
still record no usage either way - those LangChain classes have no
equivalent flag.

Estimated USD cost (`zuno.model_cost_usd`) follows that same usage-gated
posture for remote/SaaS providers - billed per-1K-token, so no usage means
no known cost. Local providers (`local`, `local-gpt-oss`) have no
per-token meter and are billed per-second of call duration instead
(`_COST_PER_SECOND_LOCAL`, apportioned from this cluster's actual GPU node
economics per ADR-0351), so their cost is recorded unconditionally -
whether the call succeeded or errored, since GPU time is consumed either
way.

## Local development

```bash
cd components/ai-gateway
docker build -t zuno/ai-gateway:local .
docker run -p 8080:8080 \
  -e KEYCLOAK_ISSUER=https://keycloak-zuno.apps.mycluster.example.com/realms/zuno \
  -v $(pwd)/../../platform/ai-gateway/provider-routing.yaml:/app/config/provider-routing.yaml:ro \
  zuno/ai-gateway:local
```
