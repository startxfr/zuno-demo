# agent-frontend

A small Go HTTP server (`net/http`, standard library only for the server
itself) that serves two PatternFly React single-page apps from one binary,
per ADR-0008 ("one frontend ... deployment per agent", same shared
codebase):

1. **The agent portal** (`GET /`) - one tile per agent, read at startup from
   every `agents/<name>/agent.okf.md` OKF v0.2 Markdown bundle (ADR-0038)
   baked into the image (see `Dockerfile`). A tile is clickable only if the
   agent's `zuno.status` is `active` **and** the signed-in user's JWT
   `groups` claim intersects the agent's `zuno.access.groups` - the
   `agent_<name>` entitlement group (ADR-0040), not a business role;
   otherwise it renders disabled ("coming soon" or "not authorized"). See
   `platform/architecture/agent-platform-separation.md`.
2. **The Tekos chat UI** (`GET /tekos`, `POST /api/chat`) - the one agent
   this v0 deployment actually runs a chat surface for, selected by the
   `ACTIVE_AGENT` env var. `POST /api/chat` is proxied server-side to the
   agent's BFF (see `components/agent-bff/README.md`), attaching the
   caller's OIDC access token as a Bearer credential, and streams token by
   token when the browser asks for it (ADR-0045 - see "Streaming chat
   (ADR-0045)" below).

## PatternFly React frontend (ADR-0044)

`web/` is a small Vite + React + TypeScript project (`web/src/portal`,
`web/src/chat`) built against the real `@patternfly/react-core` package -
this replaced an earlier hand-rolled CSS approximation of PatternFly that
existed only because this environment was believed to have no npm registry
access; that constraint no longer holds (verified in this phase: `npm
install`, a real `@patternfly/chatbot`/`@patternfly/react-core` fetch, and
downloading a Node 20 toolchain from nodejs.org all succeeded), so this ADR
now vendors the genuine library instead of approximating it.

Each Go-rendered page (`internal/portal`, `internal/chat`) is a thin,
per-request HTML shell: `<div id="root">` plus a
`<script id="zuno-config" type="application/json">` blob of server-computed
state (signed-in session, portal tiles, agent display name - see
`web/src/shared/types.ts`), which the corresponding Vite entry
(`web/src/portal/main.tsx` / `web/src/chat/main.tsx`) reads and mounts a
React tree into. This is ADR-0044's "keep runtime API endpoint injection
from environment into JavaScript context": per-deployment/per-request
values can't be baked into the static JS bundle at `npm run build` time,
so they're injected into the HTML Go renders instead.

`internal/assets` resolves each entry's actual, content-hashed
filename from `web/dist/.vite/manifest.json` (Vite's own documented
["backend integration"](https://vite.dev/guide/backend-integration)
pattern) - including a small transitive walk over the manifest's `imports`
graph, since an entry's own `css` field only lists CSS it imports
*directly*, not CSS pulled in by a shared chunk (e.g. the PatternFly base
stylesheet, which both entries import and Vite/Rollup places in a shared
chunk rather than duplicating).

### Building the web assets

```sh
cd components/agent-frontend/web
npm ci          # installs exactly what package-lock.json pins
npm run build   # tsc --noEmit type-check, then vite build -> dist/
```

`main.go` reads `web/dist/.vite/manifest.json` at startup and fails fast
if it's missing - `npm run build` must run before `go run .`/`go build`
serves real traffic (the `Dockerfile`'s `webbuild` stage does this
automatically for the container image). `npm run dev` runs Vite's own dev
server with hot reload for iterating on `web/src` without rebuilding the
Go binary each time (point it at a running BFF via its own dev proxy
config if you need `/api/chat` to resolve - not wired up here since this
component's own dev loop normally goes through the full `go run .` server).

## Streaming chat (ADR-0045)

`POST /api/chat` behaves as a synchronous JSON request by default. When
the browser sends `Accept: text/event-stream` (the PatternFly chat client
in `web/src/chat/Chat.tsx` always does), this server instead proxies the
BFF's SSE response through byte-for-byte, flushing after every chunk read
(`internal/chat/chat.go:proxySSE`) rather than buffering it - preserving
per-token latency through this hop. The wire format (unchanged end to end
from `components/agent-runtime/app/main.py:_sse` through
`components/agent-bff`) is:

- `event: start` - `{"request_id": "..."}`, the first frame, carrying the
  `X-Zuno-Request-Id` this frontend minted (or forwarded, if already
  present) for cross-service log correlation (ADR-0045 "preserve request
  correlation ... across the chain").
- `event: tool` - `{"name": "search_confluence", "status": "started"|"finished"}`,
  emitted around a live tool call so the UI can show e.g. "Using
  search_confluence…".
- `event: token` - `{"delta": "<next text fragment>"}`, one per model
  token/chunk.
- `event: done` - `{"citations": [...]}`, terminal on success.
- `event: error` - `{"message": "..."}`, terminal instead of `done` if the
  graph raises mid-stream.

A `fetch()` + `ReadableStream` reader is used client-side instead of
`EventSource` (`web/src/shared/sse.ts`), since the chat call is a `POST`
with a JSON body and a same-origin session cookie - `EventSource` can only
express a plain `GET`. The "Stop" button in the chat UI calls
`AbortController.abort()`, which closes the underlying fetch; that
propagates as a canceled `r.Context()` through this server -> the BFF ->
the Agent Runtime (ADR-0045 "client cancellation" - see each hop's own
`proxySSE`/`ChatStream` comments for exactly how).

Auth/authorization failures (missing session, wrong entitlement, invalid
body) are decided *before* this server decides whether to stream, so they
always return a plain JSON error body with the appropriate status code
regardless of the request's `Accept` header - never a truncated SSE
stream.

## Why standard library only (server-side Go)

One deliberate, still-current departure from "use the well-known library":

- **OIDC (`internal/oidc`)**: hand-rolled Authorization Code + PKCE flow
  against Keycloak using only `net/http`/`crypto/rsa`/`encoding/json`,
  instead of `golang.org/x/oauth2` + `github.com/coreos/go-oidc`. This
  wasn't about network access (see above) - the flow (RFC 6749 §4.1,
  RFC 7636, OIDC Core §3.1) is small enough to implement directly and keep
  fully auditable within this component's own small dependency surface.
  **v1 hardening recommendation**: switch to `coreos/go-oidc` for stricter
  claim validation (`nonce` replay checks, clock-skew tolerance, discovery
  caching with correct `Cache-Control` honoring) that this minimal
  implementation does not attempt.

The one non-stdlib Go dependency is `gopkg.in/yaml.v3`, used only to parse
`agent.okf.md`'s YAML frontmatter (a single, stable, widely audited API
surface) - see `go.mod`/`go.sum`.

## Configuration (environment variables)

| Variable | Required | Purpose |
|---|---|---|
| `LISTEN_ADDR` | no (default `:8080`) | HTTP listen address |
| `AGENTS_DIR` | no (default `/agents`, set to `/app/agents` in the image) | Directory of `<name>/agent.okf.md` bundles |
| `WEB_DIST_DIR` | no (default `web/dist`, set to `/app/web/dist` in the image) | Vite build output directory (ADR-0044) - see `internal/assets` |
| `ACTIVE_AGENT` | no (default `tekos`) | Which agent this deployment renders a chat UI for |
| `KEYCLOAK_ISSUER_URL` | **yes** | `https://keycloak.apps.<cluster-domain>/realms/zuno` |
| `OIDC_CLIENT_ID` | no (default `tekos-frontend`) | Keycloak client ID, contract: `<agent>-frontend` |
| `OIDC_CLIENT_SECRET` | **yes** | From an `ExternalSecret` (ADR-0024), never hardcoded |
| `OIDC_REDIRECT_URL` | no (derived from `SELF_BASE_URL` + `/callback`) | Must match the Keycloak client's registered redirect URI |
| `SELF_BASE_URL` | **yes** | `https://tekos.apps.<cluster-domain>` |
| `BFF_BASE_URL` | no (default `http://tekos-bff.zuno-agent-tekos.svc.cluster.local:8080`) | In-cluster BFF Service URL |
| `SESSION_HMAC_SECRET` | **yes** | Signs the opaque session-ID cookie (ADR-0042); from an `ExternalSecret` |
| `SESSION_ENCRYPTION_KEY` | **yes** | 32 bytes, base64-encoded (AES-256); encrypts session records at rest in Redis (ADR-0042); from an `ExternalSecret` |
| `REDIS_ADDR` | no (default `zuno-redis-master.zuno-auth.svc.cluster.local:6379`) | Server-side session store (ADR-0042) |
| `REDIS_PASSWORD` | **yes** | From an `ExternalSecret` |
| `SESSION_MAX_LIFETIME_SECONDS` | no (default `43200`, 12h) | How long a session record survives in Redis regardless of access-token refreshes (ADR-0042) |

## Keycloak hostname

`KEYCLOAK_ISSUER_URL`'s host is `keycloak.<cluster_base_domain>` (e.g.
`keycloak.apps.mycluster.example.com`), matching the Keycloak CR's actual
Route hostname (`gitops/charts/keycloak/templates/keycloak.yaml`). This
component uses a confidential OIDC client per agent (`<agent>-frontend`)
that supports the Authorization Code + PKCE flow with a client secret.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Agent portal (tile grid) |
| GET | `/login` | Begins the OIDC Authorization Code + PKCE redirect |
| GET | `/callback` | OIDC redirect URI; exchanges the code, creates the server-side session record and sets the opaque session-ID cookie (ADR-0042) |
| GET | `/logout` | Revokes the server-side session record, clears the cookie, redirects through Keycloak RP-initiated logout |
| GET | `/tekos` | Chat UI for the active agent (401→redirect to `/login` if not signed in; 403 if signed in but not authorized) |
| POST | `/api/chat` | `{"session_id","message"}` → proxied to the BFF; JSON `{"reply","citations"}`, or SSE if `Accept: text/event-stream` (ADR-0045, see above) |
| GET | `/healthz` | Liveness/readiness probe target, also used by `ansible/roles/agents/tasks/check.yml`'s smoke check |
| GET | `/static/*` | Vite-built JS/CSS assets (`web/dist`, ADR-0044) |

## Local layout

```text
main.go                    Wiring: config, OKF load, Vite manifest, routes
internal/assets/           Vite manifest.json resolution (ADR-0044)
internal/config/           Environment-variable loading
internal/okf/               agent.okf.md Markdown-frontmatter parsing (mirrors platform/okf/schema)
internal/oidc/              Hand-rolled OIDC Authorization Code + PKCE + JWKS/RS256 verification
internal/reqid/             X-Zuno-Request-Id minting/propagation (ADR-0045)
internal/session/           Opaque session-ID cookie (HMAC-signed) resolved against a
                            Redis-backed, AES-256-GCM-encrypted server-side store, with
                            transparent access-token refresh (ADR-0042)
internal/portal/            Portal page shell + config injection
internal/chat/               Chat page shell + BFF proxy (JSON and SSE)
web/                         Vite + React + TypeScript + PatternFly (ADR-0044) - see web/package.json
```

## Build

```sh
# from the repository root - build context matters, see Dockerfile
docker build -f components/agent-frontend/Dockerfile -t zuno/agent-frontend:dev .
```

The `Dockerfile` has three stages: a `node:20-alpine` stage builds `web/`
(`npm ci && npm run build`), a `golang:1.22` stage builds the server, and a
UBI9-minimal runtime stage copies both outputs. `go build ./...` (server)
and `npm run build` (web, verified against a locally-fetched Node 20
toolchain, tsc + vite both clean) were both run successfully in this
phase's development environment.
