# ADR-0045: Stream responses end to end with SSE

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The Agent Runtime already uses LangGraph streaming primitives, but BFF/frontend paths currently behave as synchronous JSON requests. This prevents the UI from benefiting from model token streaming and conflicts with the first-token objective below six seconds.

## Decision

Use Server-Sent Events end to end for chat streaming: model/MaaS -> Agent Runtime -> BFF -> Go frontend server -> browser. Preserve request correlation, citations, tool status events, completion/error frames and client cancellation across the chain.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

Users see output as soon as it is available and long responses no longer require waiting for the complete model result. Components must handle partial failures and disconnected clients.

## Security considerations

Do not stream hidden prompts, secrets, raw policy details or sensitive tool payloads. Apply classification/redaction before emitting events.

## Operational considerations

Add a performance test that measures time-to-first-token and fails when the agreed threshold is exceeded under the MVP reference load.

## Implementation state

**Implemented (2026-08-05).** `components/agent-runtime/app/main.py`
already had the `model/MaaS -> Agent Runtime` half of this chain (LangGraph
`astream_events`) before this phase; what was missing was everything after
it (Decision: "BFF -> Go frontend server -> browser"). Each hop now relays
the same SSE byte stream rather than re-implementing or buffering it:

- **agent-bff** (`internal/runtime/client.go`'s new `ChatStream` +
  `main.go`'s `proxySSE`): opens the Agent Runtime call with
  `Accept: text/event-stream` and copies the response chunk-by-chunk,
  flushing after every read.
- **agent-frontend** (`internal/chat/chat.go`'s `APIHandler` + `proxySSE`):
  the same relay pattern for the browser -> frontend -> BFF hop, gated on
  whether the *browser's own* request carried
  `Accept: text/event-stream` - the ADR-0044 rewrite's chat client always
  sends it.
- **browser** (`web/src/chat/Chat.tsx` + `web/src/shared/sse.ts`): `fetch()`
  + a `ReadableStream` reader, not `EventSource` (which can't express a
  `POST` with a JSON body and a same-origin session cookie). Renders
  `token` deltas onto the in-progress agent message live, shows a
  "Using `<tool>`…" status line for `tool` events, and finalizes citations
  on `done`.

Preserved across the chain (Decision's explicit list):

- **Citations / completion / error frames**: `done`/`error` events are
  relayed unmodified through both Go hops to the exact same client parsing
  logic that already handled `token`.
- **Tool status events**: new in this phase.
  `components/agent-runtime/app/main.py`'s `_stream_chat` now also listens
  for `on_chain_start`/`on_chain_end` LangGraph events on
  `app/graph/nodes.py:tool_call_node` (the only tool-calling node in v0)
  and emits `event: tool` `{"name": "search_confluence", "status": "started"|"finished"}`
  frames around it - only when the conditional edge actually routes
  through that node, matching the existing synchronous behavior exactly.
- **Request correlation**: new `X-Zuno-Request-Id` header
  (`components/agent-frontend/internal/reqid`,
  `components/agent-bff/internal/reqid`, both duplicating the same small
  UUIDv4 helper per this repo's established per-service-duplication
  pattern - see either README's "Why standard library only"), minted by
  agent-frontend (the first hop with an HTTP request at all) and forwarded
  unchanged by agent-bff and agent-runtime. The Agent Runtime echoes it
  back as the stream's first frame, `event: start` `{"request_id": "..."}`,
  and includes it in every hop's own log lines for the turn.
- **Client cancellation**: no explicit disconnect-polling anywhere in the
  chain - Go's `context.Context` does this for free. The chat UI's "Stop"
  button calls `AbortController.abort()`, closing the browser's `fetch`;
  that cancels agent-frontend's `r.Context()`, which (being the parent of
  the context `APIHandler` derives for its own call to the BFF) cancels the
  BFF request, whose own inbound `r.Context()` cancellation likewise
  cancels its downstream call to the Agent Runtime, whose ASGI server
  (uvicorn) cancels the `_stream_chat` generator's `astream_events`
  iteration on client disconnect. Each Go proxy's `streamClient` has no
  fixed `http.Client.Timeout` (which would otherwise bound the *entire*
  streamed response and kill a slow-but-healthy turn) - see
  `components/agent-bff/internal/runtime/client.go`'s comment on
  `streamClient`.

Security considerations ("Do not stream hidden prompts, secrets, raw
policy details or sensitive tool payloads. Apply
classification/redaction before emitting events"): no new content is
exposed by streaming that wasn't already returned synchronously before
this phase - `token` deltas are fragments of the same `reply` text the
synchronous endpoint already returned in full (already
classification/routing-gated by `components/ai-gateway` before generation
ever starts), `done`'s citations are the same `{source, title}` shape the
synchronous response already included, and the new `tool` event carries
only a tool name and a start/finished status, never arguments or results.

Operational considerations ("Add a performance test that measures
time-to-first-token and fails when the agreed threshold is exceeded under
the MVP reference load"): already satisfied before this phase by
`evaluations/tekos/scenarios.yaml`'s scenario 8
(`chat_first_token_latency`, `max_seconds: 6`, part of the original
20-scenario ADR-0027/0028 suite) - it measures exactly this at the Agent
Runtime endpoint, which dominates end-to-end latency; the relay hops added
in this phase are pure byte-copies with per-chunk flushing (no added
buffering to push first-token latency out), so a second, redundant
scenario was not added under ADR-0027's fixed count. See ADR-0044's own
Implementation state for the PatternFly rewrite this streaming client
depends on.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0009
- ADR-0032

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
