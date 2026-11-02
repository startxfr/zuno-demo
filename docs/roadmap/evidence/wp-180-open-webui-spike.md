# WP-180: Open WebUI spike

Answers the open questions of [ADR-0588](../../adr/0588-serve-a-general-purpose-chat-experience-with-open-webui.md)
for [WP-181](../work-packages/wp-181-install-open-webui-on-demo333.md). Source read at tag `v0.12.5`
(commit `f7ac7ee10962ddec0017f5c29b6740d9b9c5faca`, 2026-10-29), chart `open-webui-17.5.0`. Personas: `consultant-02`
and `sale-01` (shared with WP-182 and WP-184). The GPU nodes are down: model calls use a SaaS model through the
ai-gateway at C1, and MaaS errors on local models are recorded, not blocking.

**Status:** done 2026-11-02. Source read, live checks run on demo333 in the throw-away namespace `zuno-owui-scratch`
with a throw-away Keycloak client `owui-scratch`; both deleted afterwards (verified).

## 1. Version and pins

| Item | Value |
|---|---|
| Chart | `open-webui` `17.5.0` (helm.openwebui.com), `appVersion: 0.12.5` |
| Image | `ghcr.io/open-webui/open-webui:0.12.5` = index `sha256:03443b8de6b617da9d900edd09b4bf1cb0ddbfdcba6afb42c548336a0b821ded` |
| Image, slim | `ghcr.io/open-webui/open-webui:0.12.5-slim` = index `sha256:9a4db3e6c8d6174d4ed8952304115e90dcc36e9a8b98c2f8984eab321f29505e` |
| Sidecars | none needed: `ollama.enabled=false`, `pipelines.enabled=false`, `websocket.enabled=false` (single replica); `tika` and `terminals` are off by default |
| Init container | `copy-app-data` (`cp -R -n /app/backend/data/* /tmp/app-data/`), same image |
| Licence | "Open WebUI License": BSD-3 plus a branding clause (since v0.6.6); the branding is kept, the demo is under the 50-user threshold |

The chart's `route` value is a Gateway API `HTTPRoute`: WP-181 ships its own OpenShift Route.

## 2. User token to the ai-gateway: no relay

- An OpenAI connection with `auth_type: "system_oauth"` sends `Authorization: Bearer <the user's SSO access token>`
  (`backend/open_webui/utils/headers.py`, `get_headers_and_cookies`, branch `system_oauth`). Fixed `headers` of the
  connection are applied after it.
- The token comes from `get_system_oauth_token` (`utils/oauth.py`): the `oauth_session_id` cookie, else the user's most
  recent SSO session. Sessions are stored server-side, encrypted with `OAUTH_SESSION_TOKEN_ENCRYPTION_KEY` (falls back
  to `WEBUI_SECRET_KEY`).
- Refresh: `get_oauth_token` refreshes with the refresh token when the access token expires within 5 minutes
  (`utils/oauth.py`, `_refresh_token`, `grant_type=refresh_token`).
- The model list is fetched **per user, with that user's token** (`routers/openai.py`, `get_all_models` cached under
  `openai_all_models_<user.id>`, `MODELS_CACHE_TTL` 1 s by default).
- Trap: with role `user`, Open WebUI shows only models an admin has explicitly shared
  (`get_filtered_models` unless `BYPASS_MODEL_ACCESS_CONTROL=true`). The ai-gateway is the authority on models, so
  WP-181 sets `BYPASS_MODEL_ACCESS_CONTROL=true`.
- The ai-gateway's `/v1/models` is filtered by data classification and local-only, **not per user**: the WP-181
  acceptance "model list = the ai-gateway's `/v1/models`" is read that way.

**Decision: no relay.** Confirmed live (L3, L5).

## 3. MCP connection

- `TOOL_SERVER_CONNECTIONS` entries with `type: "mcp"` are resolved by `connect_mcp_server` (`utils/tools.py`).
- `auth_type: "system_oauth"` uses `OAuthTokenAuth(get_headers)`, which calls `build_tool_server_headers`: the user's
  SSO access token as bearer, **plus the connection's fixed `headers`** (so `X-Zuno-Agent: open-webui` and
  `X-Zuno-Task` travel with the user's token).
- Client: `mcp==2.3.0`, `streamable_http_client`. The zuno mcp-gateway `/mcp` answers JSON-RPC with a single
  `application/json` body (no SSE, no `GET /mcp`, no `Mcp-Session-Id`); the streamable HTTP client accepts a JSON
  response. Confirmed live (L4).
- `config.function_name_filter_list` can narrow the tools further; not used (the mcp-gateway is the authority).

## 4. OpenShift

- The upstream image is built with `UID=0 GID=0` and `HOME=/root`; `USE_PERMISSION_HARDENING` is off in the published
  image; `/app/backend/open_webui/static` is group-writable (`chmod -R g=u`).
- The rendered chart sets no `securityContext` (podSecurityContext and containerSecurityContext `{}`): it is left to
  the SCC, as ADR-0588 requires.
- Writable paths: `/app/backend/data` (the volume: database, uploads, caches), `/app/backend/open_webui/static`,
  `$HOME/.cache`. `WEBUI_SECRET_KEY` is set from Vault, so `start.sh` never writes `.webui_secret_key`.
- `OFFLINE_MODE=true` stops every Hugging Face download and update check.
- **The upstream image starts under `restricted-v2`** (live check L1: arbitrary UID `1001180000`, Ready, no SCC
  grant). No hardened rebuild is needed. `HOME` is set to a path under the volume.
- With the volume mounted over `/app/backend/data` and `OFFLINE_MODE=true`, the baked embedding model is not found and
  the start logs a `LocalEntryNotFoundError` from `get_ef`. It is harmless (retrieval is bypassed). The chart's
  `copy-app-data` init container seeds the volume and avoids it in WP-181.

## 5. Switches off (environment, locked)

`ENABLE_PERSISTENT_CONFIG=False` makes the environment win on every start: settings cannot drift through the admin UI.
OAuth settings are read from the environment on every start anyway (`ENABLE_OAUTH_PERSISTENT_CONFIG` defaults to False).

| Concern | Variables |
|---|---|
| Local sign-up and password login | `ENABLE_SIGNUP=False`, `ENABLE_LOGIN_FORM=False`, `ENABLE_PASSWORD_AUTH=False` |
| Ollama | `ENABLE_OLLAMA_API=False` (also implied by the chart when `ollama.enabled=false`) |
| RAG and upload | `BYPASS_EMBEDDING_AND_RETRIEVAL=True`, `USER_PERMISSIONS_CHAT_FILE_UPLOAD=False`, `USER_PERMISSIONS_CHAT_WEB_UPLOAD=False` |
| Web search | `ENABLE_WEB_SEARCH=False` |
| Image generation | `ENABLE_IMAGE_GENERATION=False` |
| Community | `ENABLE_COMMUNITY_SHARING=False` |
| User-added connections and tool servers | `ENABLE_DIRECT_CONNECTIONS=False`, `ENABLE_DIRECT_INTEGRATIONS=False` |
| Code execution | `ENABLE_CODE_EXECUTION=False`, `ENABLE_CODE_INTERPRETER=False` |
| Outbound checks | `OFFLINE_MODE=True`, `ENABLE_VERSION_UPDATE_CHECK=False` |

Functions and pipelines: no pipelines service is deployed, and with `ENABLE_PERSISTENT_CONFIG=False` an admin cannot
add a connection that survives a restart. `/api/config` still reports `enable_functions`, `enable_tools` and
`enable_plugins` true: functions can only be added by an admin, and the only admin is the `openwebui_admin` group.

**Connection access trap.** A tool-server connection with no `config.access_grants` is admin-only
(`has_connection_access`, `utils/access_control`): users get `404 Tool not found`. The MCP connection needs
`"access_grants": [{"principal_type": "user", "principal_id": "*", "permission": "read"}]`; the mcp-gateway is the
authority on what each user sees.

## 6. Keycloak

- Client `open-webui` in realm `zuno`, shape of `unifai`: confidential, standard flow, no direct grants, redirect
  `https://<route host>/oauth/oidc/callback`; mappers `groups` (`full.path: true`), `audience-self`,
  `maas-gateway-audience` (`zuno-admin-api`, since the ai-gateway forwards the caller's token to MaaS).
- `OPENID_PROVIDER_URL` is the Route issuer `https://keycloak.<apps domain>/realms/zuno/.well-known/openid-configuration`.
  Never the in-cluster `http` service: the gateways require the exact `https` issuer.
- Roles: `ENABLE_OAUTH_ROLE_MANAGEMENT=True`, `OAUTH_ROLES_CLAIM=groups`, `OAUTH_ALLOWED_ROLES=*`,
  `OAUTH_ADMIN_ROLES=/openwebui_admin`. A user whose groups match none is refused (`get_user_role`).
- **First-user trap.** `get_user_role` makes the only user of the database `admin`, before role management applies.
  Without care, the first persona to sign in becomes admin. WP-181 sets `WEBUI_ADMIN_EMAIL` and `WEBUI_ADMIN_PASSWORD`
  (Vault, random) so an inert local account takes slot 1 at first start. Password login is off, so that account cannot
  sign in. `OAUTH_MERGE_ACCOUNTS_BY_EMAIL` stays off, and the email belongs to no persona.
- The new group `openwebui_admin` is not created by the client-reconcile Job (it only creates `agent_*` groups): the
  WP-181 role creates it and its membership live, create-only.

## Live checks (demo333, 2026-11-02)

Setup: image `0.12.5` by digest, one replica, `emptyDir`, the variables of section 5, one OpenAI connection and one MCP
connection in `system_oauth`; personas signed in through the real Keycloak form (Playwright).

| Check | Result |
|---|---|
| L1 Pod under `restricted-v2` with the upstream image | **Pass.** SCC `restricted-v2`, UID `1001180000`, Ready. The bootstrap account `WEBUI_ADMIN_EMAIL` was created at first start. |
| L2 Sign-in and lockdown | **Pass.** `consultant-02` and `sale-01` signed in through Keycloak with role `user`. `POST /api/v1/auths/signup` returned 403, `POST /api/v1/auths/signin` returned 403, and the login page has no password field. |
| L3 Model list and chat | **Pass.** `/api/models` lists the ai-gateway's 11 models, fetched with the user's token. A chat reached `openai` after the fallback chain. In raw Prometheus (thanos-querier), `zuno_model_calls_total{client="other",provider="openai",outcome="success"}` appeared. It is `other` because the scratch client `owui-scratch` is outside `EXPERIENCE_CLIENTS`, which also proves the bounding. `client="open-webui"` comes with WP-181's real client. |
| L4 MCP | **Pass.** With `X-Zuno-Agent: open-webui` (not yet declared), `tools/list` is `[]` for both personas. A second connection without the header (front door) gives `consultant-02` 5 tools (`confluence.page.search`, `confluence.page.read`, `knowledge.tech.search`, `aap.platform.audit`, `aap.cluster.audit`) and `sale-01` none. Filtering is per user, through Open WebUI. |
| L5 Token expiry | **Pass.** A saved session reused 17 min after sign-in (access token lifespan 900 s): Open WebUI logged `Successfully refreshed token`, and models and MCP answered 200. |
| L6 Guardrails | **Partial.** `zuno_guardrails_evaluations_total{client="other",outcome="unavailable"}` carries the label. The NeMo backend was unavailable (observe mode, response unaffected), so a blocking prompt could not be shown. To be rerun in WP-181. |

Platform findings (owner: WP-179 session, WP-188 candidate; not Open WebUI defects):

- With the GPU nodes down, a C1 chat walks the local providers first. Each `*-maas` candidate fails after about 60 s
  plus client retries, so the SaaS answer came after about 10 minutes. Behind the default 30 s router timeout, the
  browser gets a 504 while the call goes on.
- The guardrails backend answered `unavailable` during the test.

Not run in the spike, left to WP-181 acceptance: admin role from `/openwebui_admin` (the group does not exist yet),
egress denial to the internet (the scratch namespace had no egress policy).

## Values for WP-181

- Chart `open-webui` `17.5.0`; image `ghcr.io/open-webui/open-webui@sha256:03443b8de6b617da9d900edd09b4bf1cb0ddbfdcba6afb42c548336a0b821ded`.
- `ollama.enabled=false`, `pipelines.enabled=false`, `websocket.enabled=false`, `replicaCount=1`, security
  contexts unset, persistence on the resolved StorageClass.
- Route: own OpenShift Route, edge, with `haproxy.router.openshift.io/timeout: 5m` (non-streamed calls outlast the
  30 s default).
- Secrets from Vault: `WEBUI_SECRET_KEY`, `OAUTH_SESSION_TOKEN_ENCRYPTION_KEY`, `WEBUI_ADMIN_PASSWORD`,
  `OAUTH_CLIENT_SECRET` (`keycloak/open-webui`).
- Environment:

```text
WEBUI_URL=https://open-webui.<apps domain>
ENABLE_PERSISTENT_CONFIG=False
OFFLINE_MODE=True
ENABLE_VERSION_UPDATE_CHECK=False
WEBUI_ADMIN_EMAIL=open-webui-bootstrap@invalid.zuno
ENABLE_SIGNUP=False
ENABLE_LOGIN_FORM=False
ENABLE_PASSWORD_AUTH=False
ENABLE_OAUTH_SIGNUP=True
OAUTH_PROVIDER_NAME=Zuno Keycloak
OPENID_PROVIDER_URL=https://keycloak.<apps domain>/realms/zuno/.well-known/openid-configuration
OAUTH_CLIENT_ID=open-webui
OAUTH_SCOPES=openid email profile
ENABLE_OAUTH_ROLE_MANAGEMENT=True
OAUTH_ROLES_CLAIM=groups
OAUTH_ALLOWED_ROLES=*
OAUTH_ADMIN_ROLES=/openwebui_admin
ENABLE_OAUTH_ID_TOKEN_COOKIE=False
BYPASS_MODEL_ACCESS_CONTROL=True
ENABLE_OLLAMA_API=False
ENABLE_OPENAI_API=True
OPENAI_API_BASE_URLS=http://ai-gateway.zuno-ai-run.svc:8080/v1
OPENAI_API_KEYS=
OPENAI_API_CONFIGS={"0":{"enable":true,"auth_type":"system_oauth","headers":{"X-Zuno-Data-Classification":"C1","X-Zuno-Agent":"open-webui","X-Zuno-Task":"chat"}}}
TOOL_SERVER_CONNECTIONS=[{"type":"mcp","url":"http://mcp-gateway.zuno-ai-run.svc:8080/mcp","path":"","auth_type":"system_oauth","key":"","headers":{"X-Zuno-Agent":"open-webui","X-Zuno-Task":"chat"},"config":{"enable":true,"access_grants":[{"principal_type":"user","principal_id":"*","permission":"read"}]},"info":{"id":"zuno-mcp","name":"Zuno tools"}}]
BYPASS_EMBEDDING_AND_RETRIEVAL=True
USER_PERMISSIONS_CHAT_FILE_UPLOAD=False
USER_PERMISSIONS_CHAT_WEB_UPLOAD=False
ENABLE_WEB_SEARCH=False
ENABLE_IMAGE_GENERATION=False
ENABLE_COMMUNITY_SHARING=False
ENABLE_DIRECT_CONNECTIONS=False
ENABLE_DIRECT_INTEGRATIONS=False
ENABLE_CODE_EXECUTION=False
ENABLE_CODE_INTERPRETER=False
```

- Agent and task: `X-Zuno-Agent: open-webui` and `X-Zuno-Task: chat` on both connections. The model connection
  carries them too, so a routing preference can be declared for Open WebUI. The agent `open-webui`, its
  `access_groups` and its `chat` task (knowledge and Confluence tools) are declared in `zuno-demo-agents`.
- Keycloak: client `open-webui` (section 6) and group `openwebui_admin`, created live by the role. Who belongs to it
  is set at WP-181.
