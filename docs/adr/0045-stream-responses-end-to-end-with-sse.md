# ADR-0045: Stream responses end to end with SSE

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The Agent Runtime already uses LangGraph streaming primitives, but BFF/frontend paths currently behave as synchronous JSON requests. This prevents the UI from benefiting from model token streaming and conflicts with the first-token objective below six seconds.

## Decision

Use Server-Sent Events end to end for chat streaming: model/MaaS -> Agent Runtime -> BFF -> Go frontend server -> browser. Preserve request correlation, citations, tool status events, completion/error frames and client cancellation across the chain.

## Consequences

Users see output as soon as it is available and long responses no longer require waiting for the complete model result. Components must handle partial failures and disconnected clients.

## Security considerations

Do not stream hidden prompts, secrets, raw policy details or sensitive tool payloads. Apply classification/redaction before emitting events.

## Operational considerations

Add a performance test that measures time-to-first-token and fails when the agreed threshold is exceeded under the MVP reference load.

## Implementation state

**Implemented (2026-08-05).** The Agent Runtime already had the `model/MaaS -> Agent Runtime` half of this chain (LangGraph `astream_events`); this phase added everything after it. Each hop relays the same SSE byte stream rather than re-implementing or buffering it:

- **agent-bff** (`internal/runtime/client.go`'s new `ChatStream` + `main.go`'s `proxySSE`): opens the Agent Runtime call with `Accept: text/event-stream` and copies the response chunk-by-chunk, flushing after every read.
- **agent-frontend** (`internal/chat/chat.go`'s `APIHandler` + `proxySSE`): same relay pattern for browser -> frontend -> BFF, gated on the browser's own `Accept: text/event-stream` header - the ADR-0044 chat client always sends it.
- **browser** (`web/src/chat/Chat.tsx` + `web/src/shared/sse.ts`): `fetch()` + a `ReadableStream` reader, not `EventSource` (can't express a `POST` with a JSON body and a same-origin session cookie). Renders `token` deltas live, shows a "Using `<tool>`…" status line for `tool` events, finalizes citations on `done`.

Preserved across the chain:

- **Citations/completion/error**: `done`/`error` events relayed unmodified through both Go hops to the existing client parsing logic.
- **Tool status events** (new): `components/agent-runtime/app/main.py`'s `_stream_chat` listens for `on_chain_start`/`on_chain_end` on `app/graph/nodes.py:tool_call_node` (the only tool-calling node in v0) and emits `event: tool` `{"name": "search_confluence", "status": "started"|"finished"}` frames around it.
- **Request correlation** (new `X-Zuno-Request-Id` header, duplicated small UUIDv4 helper in `agent-frontend`/`agent-bff` per this repo's per-service-duplication convention): minted by agent-frontend, forwarded unchanged by agent-bff and agent-runtime; the Runtime echoes it back as the stream's first frame (`event: start` `{"request_id": "..."}`) and includes it in every hop's log lines.
- **Client cancellation**: no explicit disconnect-polling - Go's `context.Context` propagation handles it for free, chained from the browser's `AbortController.abort()` through agent-frontend -> agent-bff -> uvicorn cancelling the Runtime's `astream_events` iteration. Each Go proxy's `streamClient` has no fixed `http.Client.Timeout` (which would otherwise bound the entire streamed response and kill a slow-but-healthy turn).

Security: no new content is exposed by streaming that wasn't already returned synchronously - `token` deltas are fragments of the same `reply` text (already classification/routing-gated by `ai-gateway` before generation starts), `done`'s citations are the same shape as before, and `tool` events carry only a name and status, never arguments or results.

Operational (performance test): already satisfied by `evaluations/tekos/scenarios.yaml` scenario 8 (`chat_first_token_latency`, `max_seconds: 6`, part of the original ADR-0027/0028 suite) - it measures this at the Agent Runtime endpoint, which dominates end-to-end latency; the relay hops added here are pure byte-copies with per-chunk flushing, so a second scenario wasn't added.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.

## Related ADRs

- ADR-0009
- ADR-0032
