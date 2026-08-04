# agent-runtime

Shared stateful orchestration runtime (ADR-0009): owns task orchestration,
LangChain/LangGraph workflows, RAG invocation and MCP tool invocation,
kept separate from model routing/quotas/fallback — that's
`components/ai-gateway`'s job. `app/clients/model_router.py` is a thin
client: it builds a `langchain_openai.ChatOpenAI` pointed at
`AI_GATEWAY_URL`, and the gateway resolves classification-eligible
providers and fallback order server-side (ADR-0020/0021). See
`components/ai-gateway/README.md` for why this split needs zero changes to
this service's LangGraph streaming mechanism.

v0 implements **one** agent workflow: Tekos (technical consultants) — the
first vertical slice per MEMORY.md section 9. The other four agents are
access-gated placeholder tiles with no runtime workflow yet.

Implementation: FastAPI (Python 3.11) + LangChain + LangGraph. Deployed by
a chart at `gitops/charts/agent-runtime` into the shared `zuno-platform`
namespace (wired up by whichever track owns the BFF/agent-surface — see
`gitops/apps/README.md`; this repo currently only builds the AI/model
layer's own GitOps apps, listed in that file).

## HTTP API contract

### `POST /v1/agents/tekos/chat`

- **Auth:** `Authorization: Bearer <keycloak-jwt>` (required).
- **Request body:**
  ```json
  { "session_id": "abc123", "user_sub": "f47ac10b-58cc-...", "message": "How do I size an InferenceService for an L4 GPU?" }
  ```
- **Response `200` (synchronous, default):**
  ```json
  {
    "reply": "For a single NVIDIA L4 (24GB)...",
    "citations": [
      { "source": "https://docs.redhat.com/...", "title": "vLLM ServingRuntime" },
      { "source": "https://confluence.example.internal/wiki/spaces/TECH/pages/123456789", "title": "OpenShift AI 3.5 EA2 - Model Serving Runbook" }
    ]
  }
  ```
- **Streaming:** send `Accept: text/event-stream` on the same request to
  receive Server-Sent Events instead:
  - `event: token` — `{"delta": "<next text fragment>"}`, one per model
    token/chunk as the `reason` node's chat model streams.
  - `event: done` — `{"citations": [...]}`, emitted once at the end (same
    shape as the synchronous response's `citations` field).
  - `event: error` — `{"message": "..."}`, emitted (instead of `done`) if
    the graph raises mid-stream.
- **Response `401`:** missing/invalid/expired JWT.
- **Response `500`:** unhandled graph failure (see `errors` accumulated in
  graph state via logs — not currently surfaced in the HTTP response body
  beyond the summary message).

### `GET /healthz` / `GET /readyz`

Both always `200` for this service today — it holds no required external
state at startup beyond what individual node calls handle defensively
per-request (retrieve/tool_call/reason each degrade gracefully rather than
crash the whole request — see `app/graph/nodes.py`).

## The Tekos workflow (LangGraph)

`app/graph/build.py` compiles an explicit `StateGraph` (`app/graph/state.py`
defines `AgentState`):

```
START -> retrieve -> [conditional] -> reason -> respond -> END
                    \-> tool_call -/
```

- **`retrieve`** (`app/graph/nodes.py:retrieve_node`) — calls
  `rag-service` `POST /v1/search` for technical documents relevant to the
  question (ADR-0018's OGX retrieval substrate). Degrades to an empty
  result set (logged) if rag-service is unreachable, rather than failing
  the whole request.
- **conditional edge** (`should_call_tools`) — a v0 heuristic (regex over
  the question for words like "confluence", "latest", "internal doc...")
  decides whether the live-data tool step is worth the extra round trip.
  This stands in for what should eventually be an OKF-declared task
  capability check once Track E authors `agents/tekos/tasks` /
  `agents/tekos/tools` (currently stubs) — see the docstring in
  `app/graph/nodes.py` for the full rationale.
- **`tool_call`** (`tool_call_node`) — calls the MCP Gateway's
  `POST /v1/tools/search_confluence/invoke`, forwarding the caller's own
  Bearer JWT (ADR-0013) and a declared `X-Zuno-Data-Classification: C1`
  (technical-docs, per `policies/data-classification/classification.yaml`).
  Degrades to no tool context (logged) if the gateway denies or fails the
  call.
- **`reason`** (`reason_node`) — builds a grounded prompt from retrieved
  docs + tool results, then calls `ModelRouter.invoke_with_fallback()`
  (`app/clients/model_router.py`), a single HTTP call to
  `components/ai-gateway`'s `POST /v1/chat/completions`. The gateway tries
  the local vLLM model first, then falls through OpenAI -> Gemini ->
  Anthropic -> Mistral in the order declared by
  `platform/ai-gateway/provider-routing.yaml`, filtered to providers
  eligible for the request's classification (ADR-0021 — fails closed,
  never silently escalates to an ineligible provider) — none of that
  fallback logic lives in this repo's `agent-runtime` code anymore
  (ADR-0009).
- **`respond`** (`respond_node`) — assembles the final
  `{reply, citations}` contract from retrieved-doc sources and any live
  Confluence results, de-duplicated.

Streaming (`app/main.py:_stream_chat`) uses LangGraph's
`astream_events(..., version="v2")` to surface `on_chat_model_stream`
events from the chat model call nested inside the `reason` node, without
needing to restructure that node into a generator itself.

## Identity propagation

Every request's Bearer JWT is validated against Keycloak's JWKS endpoint
(`app/auth.py`, same pattern as `components/mcp-gateway/app/auth.py`) and
its `groups`/`sub` claims are carried through `AgentState` so the
`tool_call` node can forward the *caller's* token to the MCP Gateway
(ADR-0013) rather than a runtime service credential.

## Configuration (env vars, no hardcoded secrets — ADR-0024)

| Var | Default | Purpose |
|---|---|---|
| `KEYCLOAK_ISSUER` | `https://keycloak-zuno.apps.example.com/realms/zuno` | JWT issuer / JWKS base |
| `RAG_SERVICE_URL` | `http://rag-service.zuno-platform.svc:8080` | retrieve node |
| `MCP_GATEWAY_URL` | `http://mcp-gateway.zuno-platform.svc:8080` | tool_call node |
| `AI_GATEWAY_URL` | `http://ai-gateway.zuno-platform.svc:8080` | reason node's `ModelRouter` (ADR-0009) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://zuno-otel-collector-collector.zuno-platform.svc:4318` | where `app/telemetry.py` sends traces (ADR-0029) |

## Observability (ADR-0029)

`app/telemetry.py` initializes an OTLP tracer at startup
(`init_telemetry()`, called from `app/main.py`) against the Collector
`ansible/roles/observability` installs — service registration only today,
no spans of its own yet. Model-call-level telemetry (per-provider spans,
token/cost metrics) moved to `components/ai-gateway/app/telemetry.py` as
part of the ADR-0009 split: that service now makes the actual provider
call, so it's the correct owner of that detail. `rag-service` and
`mcp-gateway` already have their own equivalent instrumentation.

## Local development

```bash
cd components/agent-runtime
docker build -t zuno/agent-runtime:local .
docker run -p 8080:8080 \
  -e KEYCLOAK_ISSUER=https://keycloak-zuno.apps.example.com/realms/zuno \
  -e RAG_SERVICE_URL=http://localhost:8081 \
  -e MCP_GATEWAY_URL=http://localhost:8082 \
  -e AI_GATEWAY_URL=http://localhost:8083 \
  zuno/agent-runtime:local
```
