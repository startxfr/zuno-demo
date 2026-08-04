# agent-frontend

Reusable Go HTTP server (`net/http`, standard library only) that serves two
things from one binary, per ADR-0008 ("one frontend ... deployment per
agent", same shared codebase):

1. **The agent portal** (`GET /`) — one tile per agent, read at startup from
   every `agents/<name>/agent.okf.yaml` baked into the image (see
   `Dockerfile`). A tile is clickable only if the agent's OKF `status` is
   `active` **and** the signed-in user's JWT `groups` claim intersects the
   agent's `spec.access.groups`; otherwise it renders disabled ("coming
   soon" or "not authorized"). See
   `platform/architecture/agent-platform-separation.md`.
2. **The Tekos chat UI** (`GET /tekos`, `POST /api/chat`) — the one agent
   this v0 deployment actually runs a chat surface for, selected by the
   `ACTIVE_AGENT` env var. `POST /api/chat` is proxied server-side to the
   agent's BFF (see `components/agent-bff/README.md`), attaching the
   caller's OIDC access token as a Bearer credential.

## Why standard library only

Two deliberate, documented departures from "use the well-known library":

- **OIDC (`internal/oidc`)**: hand-rolled Authorization Code + PKCE flow
  against Keycloak using only `net/http`/`crypto/rsa`/`encoding/json`,
  instead of `golang.org/x/oauth2` + `github.com/coreos/go-oidc`. This
  environment has no network access to vendor/pin those modules, and the
  flow (RFC 6749 §4.1, RFC 7636, OIDC Core §3.1) is small enough to
  implement directly and keep fully auditable. **v1 hardening
  recommendation**: once network/toolchain access exists, switch to
  `coreos/go-oidc` for stricter claim validation (`nonce` replay checks,
  clock-skew tolerance, discovery caching with correct `Cache-Control`
  honoring) that this minimal implementation does not attempt.
- **PatternFly (`static/style.css`)**: hand-rolled CSS mirroring
  PatternFly 5's tokens and class names (`pf-button`, `pf-form-control`,
  `pf-body`) rather than vendoring `@patternfly/patternfly`, again because
  there is no package-manager access here. Swapping in the real bundle
  later is a drop-in replacement since the class names already match.

The one non-stdlib dependency is `gopkg.in/yaml.v3`, used only to parse
`agent.okf.yaml` (a single, stable, widely audited API surface) — see
`go.mod`. **This repository's sandbox has no network access, so `go.sum`
was not generated here; run `go mod tidy` once real network/toolchain
access is available before building.**

## Configuration (environment variables)

| Variable | Required | Purpose |
|---|---|---|
| `LISTEN_ADDR` | no (default `:8080`) | HTTP listen address |
| `AGENTS_DIR` | no (default `/agents`, set to `/app/agents` in the image) | Directory of `<name>/agent.okf.yaml` |
| `ACTIVE_AGENT` | no (default `tekos`) | Which agent this deployment renders a chat UI for |
| `KEYCLOAK_ISSUER_URL` | **yes** | `https://sso.apps.<cluster-domain>/realms/zuno` — see assumption below |
| `OIDC_CLIENT_ID` | no (default `tekos-frontend`) | Keycloak client ID, contract: `<agent>-frontend` |
| `OIDC_CLIENT_SECRET` | **yes** | From an `ExternalSecret` (ADR-0024), never hardcoded |
| `OIDC_REDIRECT_URL` | no (derived from `SELF_BASE_URL` + `/callback`) | Must match the Keycloak client's registered redirect URI |
| `SELF_BASE_URL` | **yes** | `https://tekos.apps.<cluster-domain>` |
| `BFF_BASE_URL` | no (default `http://tekos-bff.zuno-tekos.svc.cluster.local:8080`) | In-cluster BFF Service URL |
| `SESSION_HMAC_SECRET` | **yes** | Signs the session cookie; from an `ExternalSecret` |

## Assumption flagged for the identity track

`ansible/roles/keycloak` was still a scaffold at the time this track was
built, so there is no published Keycloak route hostname convention yet.
This component assumes `sso.<cluster_base_domain>` (e.g.
`sso.apps.example.com`) as `KEYCLOAK_ISSUER_URL`'s host and a confidential
OIDC client per agent (`<agent>-frontend`) that supports the Authorization
Code + PKCE flow with a client secret. If the identity track lands a
different hostname or makes the frontend clients public (no secret), update
`gitops/charts/tekos`'s `KEYCLOAK_ISSUER_URL` value and drop
`OIDC_CLIENT_SECRET` accordingly.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Agent portal (tile grid) |
| GET | `/login` | Begins the OIDC Authorization Code + PKCE redirect |
| GET | `/callback` | OIDC redirect URI; exchanges the code, sets the session cookie |
| GET | `/logout` | Clears the session, redirects through Keycloak RP-initiated logout |
| GET | `/tekos` | Chat UI for the active agent (401→redirect to `/login` if not signed in; 403 if signed in but not authorized) |
| POST | `/api/chat` | `{"session_id","message"}` → proxied to the BFF, returns `{"reply","citations"}` |
| GET | `/healthz` | Liveness/readiness probe target, also used by `ansible/roles/agents/tasks/check.yml`'s smoke check |
| GET | `/static/*` | CSS/JS assets |

## Local layout

```text
main.go                    Wiring: config, OKF load, routes
internal/config/           Environment-variable loading
internal/okf/               agent.okf.yaml parsing (mirrors platform/okf/schema)
internal/oidc/              Hand-rolled OIDC Authorization Code + PKCE + JWKS/RS256 verification
internal/session/           Signed-cookie session (HMAC, no server-side store)
internal/portal/            Portal tile page
internal/chat/               Chat UI page + BFF proxy
static/                      CSS/JS
```

## Build

```sh
# from the repository root — build context matters, see Dockerfile
docker build -f components/agent-frontend/Dockerfile -t zuno/agent-frontend:dev .
```

Not run in this environment (no toolchain/network access here); the code is
written to compile against Go 1.22 with `go build ./...` once dependencies
are fetched via `go mod tidy`.
