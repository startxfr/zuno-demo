# agent-bff

Reusable Go HTTP service (`net/http`, standard library only - no external
Go modules at all, see `go.mod`) that sits between `components/agent-frontend`
and the shared Agent Runtime for one agent. It has no public
OpenShift Route: the frontend calls it over its in-cluster `Service` only,
forwarding the caller's OIDC access token as a Bearer credential.

## What it does

1. Validates the incoming bearer JWT's RS256 signature against Keycloak's
   JWKS, plus issuer/audience/expiry (the BFF independently revalidates
   identity rather than trusting the frontend).
2. Enforces agent entitlement server-side: the validated token's
   `groups` claim must contain `agent_<AGENT_NAME>` (e.g. `agent_tekos`),
   otherwise the call is rejected `403`. This is a distinct dimension from
   the business-role groups (`consultant`, `sales`, `adv`, `finance`,
   `board`, ...) that gate individual tools downstream at the MCP Gateway -
   a caller can hold one without the other. Frontend tile visibility
   (`components/agent-frontend/internal/portal`) is UX only, not
   authorization; this check is the actual enforcement point.
3. Calls the shared Agent Runtime's documented chat contract, forwarding
   the same validated bearer token it just checked (the Runtime requires
   this header and rejects calls without one):

   ```text
   POST {AGENT_RUNTIME_BASE_URL}/v1/agents/{AGENT_NAME}/chat
     headers: Authorization: Bearer <end-user token>
              Accept: text/event-stream (only if the frontend asked to stream)
              X-Zuno-Request-Id: <uuid> (see below)
     body:  {"session_id": string, "user_sub": string, "message": string}
     reply: {"reply": string, "citations": [{"source": string, "title": string}]}
            or an SSE stream (see the frontend's own README for the exact
            event contract) when Accept: text/event-stream was sent.
   ```

   `user_sub` is taken from the validated token's `sub` claim, but is
   informational/correlation only on the Runtime side - the Runtime
   derives the authoritative identity from the forwarded token itself,
   never from this field.
4. Relays the runtime's reply back to the frontend - either the buffered
   JSON body (default) or, when the frontend sent
   `Accept: text/event-stream`, the runtime's SSE stream relayed
   chunk-by-chunk (`main.go:proxySSE`) rather than buffered (see
   "Streaming" below).

## This service's own API surface (what the frontend calls)

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| POST | `/api/chat` | `Authorization: Bearer <access_token>` | `{"session_id": string, "message": string, "run_id": string (optional, ADR-0212), "project_id": string (optional, ADR-0209)}` | `200 {"reply": string, "citations": [{"source","title"}], "run_id": string, "source_mode": string}` (ADR-0215: `run_id` lets a synchronous caller resume the same conversation on a later turn, exactly like the SSE `start` event already did), or a relayed SSE stream if the caller sent `Accept: text/event-stream` / `401 {"error"}` if the token is missing, invalid or expired / `403 {"error"}` if the token lacks the `agent_<AGENT_NAME>` entitlement group / `400 {"error"}` on a bad request body / `502 {"error"}` if the Agent Runtime call fails |
| GET | `/api/conversations` | `Authorization: Bearer <access_token>` | `?starred=true` (optional) | `200 [{"run_id","title","updated_at","starred"}]` (ADR-0212) |
| GET | `/api/conversations/{run_id}/transcript` | `Authorization: Bearer <access_token>` | - | `200 [{"role","content","ts"}]` / `404` unknown run_id / `403` belongs to a different subject (ADR-0212) |
| PATCH | `/api/conversations/{run_id}` | `Authorization: Bearer <access_token>` | `{"title": string}` | `200 {"run_id","title"}` / `404` unknown or not owned by the caller (ADR-0212) |
| DELETE | `/api/conversations/{run_id}` | `Authorization: Bearer <access_token>` | - | `200 {"archived": bool}` / `404` unknown or not owned by the caller (ADR-0212 follow-up, soft-delete: hides the conversation, never touches its checkpoint) |
| PUT/DELETE | `/api/conversations/{run_id}/star` | `Authorization: Bearer <access_token>` | - | `200 {"starred": bool}` / `404` unknown or not owned by the caller (ADR-0212) |
| GET | `/healthz` | none | - | `200 ok` |

## Streaming

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
  client cancellation propagates for free through Go's `context` plumbing,
  no explicit disconnect-polling needed.
- **`X-Zuno-Request-Id` propagation**: `internal/reqid` forwards whatever ID
  `components/agent-frontend` minted (the normal case) or mints its own if
  called directly (e.g. `evaluations/tekos/security_checks.py`), so this
  turn's Agent Runtime log lines and its SSE `start` event carry the same
  ID as this service's own logs.

## OpenAPI contract

`openapi.json` is this service's versioned, OpenAPI 3.0.3 contract for
`GET /healthz` and `POST /api/chat` (both the synchronous JSON response
and the SSE variant, documented in prose under the `200` response since
OpenAPI 3.0 has no first-class way to type a stream of discriminated event
payloads under one response). Authored as JSON rather than YAML
specifically so `contract_test.go` can parse it with `encoding/json`
alone, preserving this component's zero-external-Go-dependency property
(see "Why standard library only" below).

**Contract test**: `contract_test.go` reads `openapi.json` and asserts
the actual Go wire structs (`apiChatRequest`, `apiChatResponse`,
`apiErrorResponse`, `internal/runtime.Citation`) serialize to exactly the
JSON field names the spec declares - a change to one without the other
fails `go test`. Run it with:

```sh
go test ./...
```

**Linting**: `platform/api/lint_openapi.py` validates `openapi.json`
against the OpenAPI 3.x meta-schema and a couple of conventions (every
non-health operation declares a security requirement; no schema property
name looks like it holds a raw token) - see that script's own docstring,
run from the repository root.

## Configuration (environment variables)

| Variable | Required | Purpose |
|---|---|---|
| `LISTEN_ADDR` | no (default `:8080`) | HTTP listen address |
| `AGENT_NAME` | no (default `tekos`) | Which agent's Agent Runtime path this BFF calls |
| `KEYCLOAK_ISSUER_URL` | **yes** | `https://keycloak.apps.<cluster-domain>/realms/zuno` |
| `OIDC_AUDIENCE` | no (default `tekos-frontend`) | Expected `aud`/`azp` claim on incoming tokens |
| `AGENT_RUNTIME_BASE_URL` | no (default `http://agent-runtime.zuno-ai-run.svc.cluster.local:8080`) | Shared Agent Runtime in-cluster base URL |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | no (default `http://zuno-otel-collector-collector.zuno-monitoring.svc:4318`) | Where OTLP metrics are sent (ADR-0029/ADR-0102, `internal/telemetry`) |

No secret is configured here: JWKS is public key material fetched over
HTTP, and this service holds no credential of its own (nothing to source
from Vault for this component).

## Assumptions flagged for other tracks

- **Identity**: JWKS validation targets Keycloak's conventional
  `<issuer>/protocol/openid-connect/certs` path directly, not a documented
  discovery contract (none exists yet). If the identity track later
  specifies a different propagation mechanism (e.g. a validated identity
  header from a sidecar instead of a raw bearer JWT), update
  `internal/jwks`.
- **Agent Runtime**: this client implements the `POST /v1/agents/{agent}/chat`
  contract. It has not been exercised against a live Agent Runtime in this
  environment (no cluster access) - `internal/runtime/client.go` is
  written to compile and to match the documented request/response shape
  precisely.

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

The one deliberate exception is `internal/telemetry` (ADR-0111, roadmap
WP-12): it pulls in the OpenTelemetry Go SDK, matching every other
service's own OTLP-to-the-shared-Collector pattern (ADR-0029) rather than
hand-rolling a narrower auditable surface the way JWT verification gets -
observability isn't a small, stable spec the way RS256/JWKS is.

## Build

```sh
docker build -t zuno/agent-bff:dev components/agent-bff
```

`go build ./...`, `go vet ./...`, `gofmt -l .` and `go test ./...` (the
`contract_test.go` suite above) validate the build.
