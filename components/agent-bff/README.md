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
     body:  {"session_id": string, "user_sub": string, "message": string}
     reply: {"reply": string, "citations": [{"source": string, "title": string}]}
   ```

   `user_sub` is taken from the validated token's `sub` claim, but is
   informational/correlation only on the Runtime side (ADR-0033) - the
   Runtime derives the authoritative identity from the forwarded token
   itself, never from this field.
4. Relays the runtime's reply back to the frontend.

## This service's own API surface (what the frontend calls)

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| POST | `/api/chat` | `Authorization: Bearer <access_token>` | `{"session_id": string, "message": string}` | `200 {"reply": string, "citations": [{"source","title"}]}` / `401 {"error"}` if the token is missing, invalid or expired / `403 {"error"}` if the token lacks the `agent_<AGENT_NAME>` entitlement group (ADR-0040) / `400 {"error"}` on a bad request body / `502 {"error"}` if the Agent Runtime call fails |
| GET | `/healthz` | none | - | `200 ok` |

## Configuration (environment variables)

| Variable | Required | Purpose |
|---|---|---|
| `LISTEN_ADDR` | no (default `:8080`) | HTTP listen address |
| `AGENT_NAME` | no (default `tekos`) | Which agent's Agent Runtime path this BFF calls |
| `KEYCLOAK_ISSUER_URL` | **yes** | `https://sso.apps.<cluster-domain>/realms/zuno` |
| `OIDC_AUDIENCE` | no (default `tekos-frontend`) | Expected `aud`/`azp` claim on incoming tokens |
| `AGENT_RUNTIME_BASE_URL` | no (default `http://agent-runtime.zuno-ai.svc.cluster.local:8080`) | Shared Agent Runtime in-cluster base URL |

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

Same reasoning as `components/agent-frontend`: no network access in this
environment to vendor/pin a JWT library, and RS256/JWKS verification is a
small, well-specified surface (RFC 7515/7517) worth keeping fully
auditable. `internal/jwks` intentionally duplicates
`components/agent-frontend/internal/oidc`'s verification code rather than
sharing a module across two independently deployed, independently
versioned services.

## Build

```sh
docker build -t zuno/agent-bff:dev components/agent-bff
```

Not run in this environment (no toolchain/network access here); the code is
written to compile against Go 1.22 with `go build ./...`.
