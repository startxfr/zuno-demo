# agent-bff

Reusable Go HTTP service (`net/http`, standard library only - no external
Go modules at all, see `go.mod`) that sits between `components/agent-frontend`
and the shared Agent Runtime for one agent (ADR-0008). It has no public
OpenShift Route: the frontend calls it over its in-cluster `Service` only,
forwarding the caller's OIDC access token as a Bearer credential.

## What it does

1. Validates the incoming bearer JWT's RS256 signature against Keycloak's
   JWKS, plus issuer/audience/expiry (ADR-0013 identity propagation - the
   BFF independently revalidates identity rather than trusting the
   frontend).
2. Enforces agent entitlement server-side (ADR-0040): the validated token's
   `groups` claim must contain `agent_<AGENT_NAME>` (e.g. `agent_tekos`),
   otherwise the call is rejected `403`. This is a distinct dimension from
   the business-role groups (`consultant`, `sales`, `adv`, `finance`,
   `board`, ...) that gate individual tools downstream at the MCP Gateway -
   a caller can hold one without the other. Frontend tile visibility
   (`components/agent-frontend/internal/portal`) is UX only, not
   authorization; this check is the actual enforcement point.
3. Calls the shared Agent Runtime's documented chat contract, owned by a
   parallel track, forwarding the same validated bearer token it just
   checked (ADR-0032 - identity must propagate all the way to the Runtime,
   not stop at the BFF; the Runtime requires this header and rejects calls
   without one):

   ```text
   POST {AGENT_RUNTIME_BASE_URL}/v1/agents/{AGENT_NAME}/chat
     headers: Authorization: Bearer <end-user token>
              Accept: text/event-stream (only if the frontend asked to stream)
              X-Zuno-Request-Id: <uuid> (ADR-0045, see below)
     body:  {"session_id": string, "user_sub": string, "message": string}
     reply: {"reply": string, "citations": [{"source": string, "title": string}]}
            or an SSE stream (see the frontend's own README for the exact
            event contract) when Accept: text/event-stream was sent.
   ```

   `user_sub` is taken from the validated token's `sub` claim, but is
   informational/correlation only on the Runtime side (ADR-0033) - the
   Runtime derives the authoritative identity from the forwarded token
   itself, never from this field.
4. Relays the runtime's reply back to the frontend - either the buffered
   JSON body (default) or, when the frontend sent
   `Accept: text/event-stream`, the runtime's SSE stream relayed
   chunk-by-chunk (`main.go:proxySSE`) rather than buffered (ADR-0045 - see
   "Streaming (ADR-0045)" below).

## This service's own API surface (what the frontend calls)

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| POST | `/api/chat` | `Authorization: Bearer <access_token>` | `{"session_id": string, "message": string}` | `200 {"reply": string, "citations": [{"source","title"}]}`, or a relayed SSE stream if the caller sent `Accept: text/event-stream` / `401 {"error"}` if the token is missing, invalid or expired / `403 {"error"}` if the token lacks the `agent_<AGENT_NAME>` entitlement group (ADR-0040) / `400 {"error"}` on a bad request body / `502 {"error"}` if the Agent Runtime call fails |
| GET | `/healthz` | none | - | `200 ok` |

## Streaming (ADR-0045)

This service is a pure relay for the streaming path, not a re-implementation
of it: `internal/runtime/client.go`'s `ChatStream` opens the same
`POST .../chat` call as the synchronous `Chat` method, but with
`Accept: text/event-stream`, and hands back the raw `*http.Response` for
`main.go:proxySSE` to copy chunk-by-chunk (flushing after every read) onto
this service's own `http.ResponseWriter`. Two things follow from that:

- **No fixed request timeout on the streaming path.** `http.Client.Timeout`
  bounds an entire request including reading the response body, which
  would kill a slow-but-healthy stream - so `ChatStream` uses a separate
  `http.Client` with no `Timeout`, and `chatHandler` instead derives a
  120-second-bounded `context.Context` from the inbound request for the
  overall call. An early client disconnect (browser closed the tab, or hit
  "Stop") cancels the inbound `r.Context()` directly, which cancels that
  derived context, which cancels the outbound call to the Agent Runtime -
  ADR-0045's "client cancellation" propagates for free through Go's
  `context` plumbing, no explicit disconnect-polling needed.
- **`X-Zuno-Request-Id` propagation** (ADR-0045 "preserve request
  correlation ... across the chain"): `internal/reqid` forwards whatever ID
  `components/agent-frontend` minted (the normal case) or mints its own if
  called directly (e.g. `evaluations/tekos/security_checks.py`), so this
  turn's Agent Runtime log lines and its SSE `start` event carry the same
  ID as this service's own logs.

## OpenAPI contract (ADR-0054)

`openapi.json` is this service's versioned, OpenAPI 3.0.3 contract for
`GET /healthz` and `POST /api/chat` (both the synchronous JSON response
and the SSE variant, documented in prose under the `200` response since
OpenAPI 3.0 has no first-class way to type a stream of discriminated event
payloads under one response). Authored as JSON rather than YAML
specifically so `contract_test.go` can parse it with `encoding/json`
alone, preserving this component's zero-external-Go-dependency property
(see "Why standard library only" below) - a YAML-parsing dependency would
otherwise have been the one exception.

**Contract test** (ADR-0054 Operational considerations: "Add ... contract
tests"): `contract_test.go` reads `openapi.json` and asserts the actual
Go wire structs (`apiChatRequest`, `apiChatResponse`, `apiErrorResponse`,
`internal/runtime.Citation`) serialize to exactly the JSON field names the
spec declares - a change to one without the other fails `go test`, the
identity/streaming drift ADR-0054's own Context names as the thing that
already happened once (`user_sub`/`session_id`/`message` naming across
components) is what this is meant to catch early the next time. Run it
with:

```sh
go test ./...
```

**Linting** (Operational considerations: "Add OpenAPI linting"):
`platform/api/lint_openapi.py` validates `openapi.json` against the
OpenAPI 3.x meta-schema and a couple of ADR-0054-specific conventions
(every non-health operation declares a security requirement; no schema
property name looks like it holds a raw token) - see that script's own
docstring, run from the repository root.

**Not part of this contract**: the ADR's own decision text also mentions
"task discovery" and "approvals" as things a BFF OpenAPI spec should
cover. Neither concept exists anywhere in this codebase (v0 is a single
chat endpoint per agent, no per-task routing UI, no approval workflow) -
`openapi.json` documents the real `/api/chat`/`/healthz` surface rather
than inventing endpoints to satisfy the ADR's generic template wording.

## Configuration (environment variables)

| Variable | Required | Purpose |
|---|---|---|
| `LISTEN_ADDR` | no (default `:8080`) | HTTP listen address |
| `AGENT_NAME` | no (default `tekos`) | Which agent's Agent Runtime path this BFF calls |
| `KEYCLOAK_ISSUER_URL` | **yes** | `https://sso.apps.<cluster-domain>/realms/zuno` |
| `OIDC_AUDIENCE` | no (default `tekos-frontend`) | Expected `aud`/`azp` claim on incoming tokens |
| `AGENT_RUNTIME_BASE_URL` | no (default `http://agent-runtime.zuno-ai-run.svc.cluster.local:8080`) | Shared Agent Runtime in-cluster base URL |

No secret is configured here: JWKS is public key material fetched over
HTTP, and this service holds no credential of its own (ADR-0024 - nothing
to source from Vault for this component).

## Assumptions flagged for other tracks

- **Identity**: `platform/identity/README.md` did not exist yet when this
  was written, so JWKS validation targets Keycloak's conventional
  `<issuer>/protocol/openid-connect/certs` path directly rather than a
  documented discovery contract. If the identity track later specifies a
  different propagation mechanism (e.g. a validated identity header from a
  sidecar instead of a raw bearer JWT), update `internal/jwks`.
- **Agent Runtime**: this client implements the `POST /v1/agents/{agent}/chat`
  contract exactly as specified in the Track E brief. It has not been
  exercised against a live Agent Runtime in this environment (no cluster
  access) - `internal/runtime/client.go` is written to compile and to match
  the documented request/response shape precisely.

## Why standard library only

Same reasoning as `components/agent-frontend`: RS256/JWKS verification is a
small, well-specified surface (RFC 7515/7517) worth keeping fully
auditable within this component's own small dependency footprint, rather
than pulling in a general-purpose JWT library for one narrow use.
`internal/jwks` intentionally duplicates
`components/agent-frontend/internal/oidc`'s verification code, and
`internal/reqid` intentionally duplicates
`components/agent-frontend/internal/reqid`'s UUIDv4 helper, rather than
sharing a module across two independently deployed, independently
versioned services.

## Build

```sh
docker build -t zuno/agent-bff:dev components/agent-bff
```

`go build ./...`, `go vet ./...`, `gofmt -l .` and `go test ./...` (the
`contract_test.go` suite above, this repository's first Go test suite)
were all run successfully against Go 1.26 in this phase's development
environment (the toolchain constraint noted in earlier phases' docs no
longer applies here - see `components/agent-frontend/README.md`'s
PatternFly section for the same finding on the npm side).
