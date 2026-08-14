# agent-runtime

Shared stateful orchestration runtime: owns task orchestration,
LangChain/LangGraph workflows, RAG invocation and MCP tool invocation,
kept separate from model routing/quotas/fallback - that's
`components/ai-gateway`'s job. `app/clients/model_router.py` is a thin
client: it builds a `langchain_openai.ChatOpenAI` pointed at
`AI_GATEWAY_URL`, and the gateway resolves classification-eligible
providers and fallback order server-side. See `components/ai-gateway/README.md`
for why this split needs zero changes to this service's LangGraph
streaming mechanism.

v0 implements **one** agent workflow: Tekos (technical consultants) - the
first vertical slice per MEMORY.md section 9. The other four agents are
access-gated placeholder tiles with no runtime workflow yet.

Implementation: FastAPI (Python 3.11) + LangChain + LangGraph. Deployed by
a chart at `gitops/charts/agent-runtime` into the shared `zuno-ai-run`
namespace (wired up by whichever track owns the BFF/agent-surface - see
`gitops/apps/README.md`; this repo currently only builds the AI/model
layer's own GitOps apps, listed in that file).

## HTTP API contract

### `POST /v1/agents/tekos/chat`

- **Auth:** `Authorization: Bearer <keycloak-jwt>` (required; the BFF forwards
  the same end-user token it validated).
- **Request body:** `user_sub` is informational/correlation only -
  the authoritative subject, groups and bearer token used for every
  downstream classification/tool/model call always come from the validated
  token, never from this field. `run_id` (optional) resumes a
  prior workflow run from its last checkpoint instead of starting a new one
  - omit it to start fresh.
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
    ],
    "run_id": "3fae9c2e-..."
  }
  ```
  Pass `run_id` back as the request's `run_id` field on a later call
  (browser disconnect, explicit "continue" action) to resume this exact
  workflow from its last checkpoint. Resuming a `run_id` whose
  checkpoint belongs to a different validated subject than the caller's own
  token is refused (`403`) - re-enforced on every resume, not just checked
  once when the run started; an unknown/expired `run_id` is `404`.
- **Streaming:** send `Accept: text/event-stream` on the same request to
  receive Server-Sent Events instead (relayed unmodified all the
  way to the browser by `components/agent-bff` and
  `components/agent-frontend`, see their own READMEs):
  - `event: start` - `{"request_id": "...", "run_id": "..."}`, the first
    frame: `request_id` echoes the `X-Zuno-Request-Id` header this request
    arrived with (or a freshly minted one if it arrived without one - see
    `app/main.py:_request_id`) so every hop's logs for this turn share one
    correlatable ID; `run_id` is this workflow's checkpoint
    thread id, to pass back on a later request to resume it.
  - `event: tool` - `{"name": "search_confluence", "status": "started"|"finished"}`,
    emitted around `tool_call_node` actually running (only when the
    conditional edge routes through it - see "The Tekos workflow" below).
  - `event: token` - `{"delta": "<next text fragment>"}`, one per model
    token/chunk as the `reason` node's chat model streams.
  - `event: done` - `{"citations": [...]}`, emitted once at the end (same
    shape as the synchronous response's `citations` field).
  - `event: error` - `{"message": "..."}`, emitted (instead of `done`) if
    the graph raises mid-stream.

  `evaluations/tekos/scenarios.yaml`'s scenario 8
  (`chat_first_token_latency`, `max_seconds: 6`) measures time-to-first-token
  at this endpoint, which dominates end-to-end latency; the BFF/frontend
  SSE relay hops are pure byte-relays that flush per-chunk.
- **Response `401`:** missing/invalid/expired JWT.
- **Response `403`:** `run_id` was supplied but its checkpoint belongs to a
  different subject than the validated caller.
- **Response `404`:** `run_id` was supplied but no checkpoint exists for it
  (unknown or expired).
- **Response `500`:** unhandled graph failure (see `errors` accumulated in
  graph state via logs - not currently surfaced in the HTTP response body
  beyond the summary message).

### `GET /healthz` / `GET /readyz`

Both always `200` for this service today - it holds no required external
state at startup beyond what individual node calls handle defensively
per-request (retrieve/tool_call/reason each degrade gracefully rather than
crash the whole request - see `app/graph/nodes.py`). This holds even with
Postgres-backed checkpointing: the app's ASGI lifespan (`app/
main.py:lifespan`) must finish building the Tekos graph - Postgres
connection included, when configured - before FastAPI serves any request
at all, so by the time either endpoint can be reached the graph is already
ready; there is no separate "checkpointer connected" state to report.

## The Tekos workflow (LangGraph)

`app/graph/build.py` compiles an explicit `StateGraph` (`app/graph/state.py`
defines `AgentState`):

```
START -> retrieve -> [conditional] -> reason -> respond -> END
                    \-> tool_call -/
```

- **`retrieve`** (`app/graph/nodes.py:retrieve_node`) - calls
  `rag-service` `POST /v1/search` for technical documents relevant to the
  question. Degrades to an empty result set (logged) if rag-service is
  unreachable, rather than failing the whole request.
  `_extract_product_version` looks for a named product/version in the
  question (e.g. "OpenShift AI 3.5") and forwards it as a deterministic
  pre-ranking filter, since similarity alone can return the wrong
  OpenShift version even when the user names one; `_detect_language`
  similarly forwards a soft French-language ranking preference when the
  question looks French. The caller's own groups are forwarded too, so
  rag-service can enforce ACL-restricted documents server-side.
  `effective_classification` escalates to the highest classification
  among the retrieved docs themselves (rag-service tags each one
  per-document) - the same escalate-never-downgrade rule `tool_call_node`
  uses for Confluence.
- **conditional edge** (`should_call_tools`) - a v0 heuristic (regex over
  the question for words like "confluence", "latest", "internal doc...")
  decides whether the live-data tool step is worth the extra round trip.
  This is intent detection: the OKF bundle governs *whether the tool is
  allowed at all* once triggered (`_ANSWER_TASK.allowed_tools`, below),
  not *when* to trigger it.
- **`tool_call`** (`tool_call_node`) - calls the MCP Gateway's
  `POST /v1/tools/search_confluence/invoke`, forwarding the caller's own
  Bearer JWT, a declared `X-Zuno-Agent: tekos` /
  `X-Zuno-Task: answer-technical-question` (the gateway's
  agent-declaration/task-rights check) and a declared
  `X-Zuno-Data-Classification: C2` (confluence, per
  `policies/data-classification/classification.yaml`, escalated from
  whatever the turn's baseline was; the tool's own `min_classification`
  requires at least C2). Degrades to no tool context (logged) if the
  gateway denies or fails the call, or if
  `agents/tekos/tasks/answer-technical-question.md` no longer declares
  `search_confluence` (checked locally before the call). On success,
  escalates `effective_classification` for the rest of the turn and, per
  the gateway's `external_model_policy.allow_context` verdict, may set
  `local_only_required` so the `reason` step below is forced to local
  inference regardless of classification.
- **`reason`** (`reason_node`) - builds a grounded prompt (system prompt
  from `agents/tekos/prompts/answer-technical-question.md`) from retrieved
  docs + tool results, then calls `ModelRouter.invoke_with_fallback()`
  (`app/clients/model_router.py`), a single HTTP call to
  `components/ai-gateway`'s `POST /v1/chat/completions`, declaring the
  turn's aggregated `effective_classification` (seeded from
  `agents/tekos/agent.okf.md`'s `zuno.model.preferred_classification`
  rather than a Python constant) and `X-Zuno-Local-Only`. The gateway
  tries the local vLLM model first, then falls through OpenAI -> Gemini
  -> Anthropic -> Mistral in the order declared by
  `platform/ai-gateway/provider-routing.yaml`, filtered to providers
  eligible for the request's classification (fails closed, never silently
  escalates to an ineligible provider) and further filtered to local-only
  when `X-Zuno-Local-Only: true` - none of that fallback logic lives in
  this repo's `agent-runtime` code anymore.
- **`respond`** (`respond_node`) - assembles the final
  `{reply, citations}` contract from retrieved-doc sources and any live
  Confluence results, de-duplicated.

Streaming (`app/main.py:_stream_chat`) uses LangGraph's
`astream_events(..., version="v2")` to surface `on_chat_model_stream`
events from the chat model call nested inside the `reason` node, without
needing to restructure that node into a generator itself.

## Agent definition

`app/registry.py`'s `AgentRegistry` loads every `agents/<name>/agent.okf.md`
OKF v0.2 Markdown bundle under `AGENTS_DIR` at import time (fails fast -
`app/graph/nodes.py` raises at module load if `tekos`'s bundle or its
`answer-technical-question` task/prompt is missing or malformed -
configuration errors must be validated early). This replaces
what used to be hardcoded Python constants:

| Was (Python constant) | Now (OKF bundle field) |
|---|---|
| `TEKOS_DATA_CLASSIFICATION` / `TEKOS_BASE_CLASSIFICATION = "C1"` | `agents/tekos/agent.okf.md`'s `zuno.model.preferred_classification` |
| `RAG_TOP_K = 5` | `agents/tekos/agent.okf.md`'s `zuno.rag.top_k` |
| the `reason` node's hardcoded system-prompt string | `agents/tekos/prompts/answer-technical-question.md` (body text) |
| the implicit "search_confluence is always available" assumption | `agents/tekos/tasks/answer-technical-question.md`'s `zuno.allowed_tools` (`tool_call_node` checks it before calling) |

`components/agent-runtime/tests/test_registry.py` is the acceptance
test proving this: it loads a temporary fixture bundle, edits it, and
asserts the registry's resolved output changes accordingly - the same
mechanism the real `agents/tekos/` bundle exercises at every service
startup.

`components/agent-runtime/tests/test_retrieve_metadata.py` is the
equivalent for the retrieval side: it asserts `_extract_product_version`
resolves "OpenShift AI 3.5"/"RHOAI 2.16"-style mentions to the right
`(product, version)` pair (and that the more specific pattern wins over
the bare "OpenShift" one), `_detect_language` returns a French preference
only when warranted, and classification escalation across retrieved docs
never downgrades. Both test files share the same no-pytest,
no-live-cluster, run-directly convention:

```bash
cd components/agent-runtime
python3 tests/test_registry.py
python3 tests/test_retrieve_metadata.py
python3 tests/test_checkpointing.py
```

`test_checkpointing.py` proves `_resolve_run_id`'s resume/
authorization logic and `build_graph`'s checkpointer wiring against a
`MemorySaver` - it implements the exact same `BaseCheckpointSaver`
interface `AsyncPostgresSaver` does (`aget_tuple`, checkpoint shape with
`channel_values`), so this exercises the real production logic without
needing a live Postgres instance.

## Identity propagation

Every request's Bearer JWT is validated against Keycloak's JWKS endpoint
(`app/auth.py`, same pattern as `components/mcp-gateway/app/auth.py`) and
its `groups`/`sub` claims are carried through `AgentState` so the
`tool_call` node can forward the *caller's* token to the MCP Gateway
rather than a runtime service credential.

## Configuration (env vars, no hardcoded secrets)

| Var | Default | Purpose |
|---|---|---|
| `KEYCLOAK_ISSUER` | `https://keycloak-zuno.apps.mycluster.example.com/realms/zuno` | JWT issuer / JWKS base |
| `RAG_SERVICE_URL` | `http://rag-service.zuno-data.svc:8080` | retrieve node |
| `MCP_GATEWAY_URL` | `http://mcp-gateway.zuno-ai-run.svc:8080` | tool_call node |
| `AI_GATEWAY_URL` | `http://ai-gateway.zuno-ai-run.svc:8080` | reason node's `ModelRouter` |
| `AGENTS_DIR` | `/app/agents` | Directory of `<name>/agent.okf.md` OKF bundles, loaded by `app/registry.py`'s `AgentRegistry` at import time |
| `CHECKPOINT_PGHOST` / `CHECKPOINT_PGPORT` / `CHECKPOINT_PGDATABASE` / `CHECKPOINT_PGUSER` / `CHECKPOINT_PGPASSWORD` | unset | LangGraph checkpointer DSN (separate vars, never a combined URI - see `app/main.py:_checkpoint_conninfo`). All four of host/database/user/password must be set or the app falls back to in-memory checkpointing (not resumable across restarts) - the documented default for local dev and every test. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://zuno-otel-collector-collector.zuno-monitoring.svc:4318` | where `app/telemetry.py` sends traces |

## Observability

`app/telemetry.py` initializes an OTLP tracer at startup
(`init_telemetry()`, called from `app/main.py`) against the Collector
`ansible/roles/observability` installs - service registration only today,
no spans of its own yet. Model-call-level telemetry (per-provider spans,
token/cost metrics) lives in `components/ai-gateway/app/telemetry.py`
instead, since that service makes the actual provider call. `rag-service`
and `mcp-gateway` already have their own equivalent instrumentation.

## Local development

```bash
# from the repository root - build context matters (bakes in agents/, see Dockerfile)
docker build -f components/agent-runtime/Dockerfile -t zuno/agent-runtime:local .
docker run -p 8080:8080 \
  -e KEYCLOAK_ISSUER=https://keycloak-zuno.apps.mycluster.example.com/realms/zuno \
  -e RAG_SERVICE_URL=http://localhost:8081 \
  -e MCP_GATEWAY_URL=http://localhost:8082 \
  -e AI_GATEWAY_URL=http://localhost:8083 \
  zuno/agent-runtime:local
```
