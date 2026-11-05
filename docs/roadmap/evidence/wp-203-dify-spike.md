# WP-203: Dify spike on demo333 (2026-11-04)

Scratch namespace `zuno-dify-scratch` (removed at the end), OpenShift 4.22.20, `restricted-v2` everywhere, no SCC granted.
Chart `dify-helm` **0.39.0** (BorisPolonsky, app 1.17.0), Helm repo `https://borispolonsky.github.io/dify-helm`.

## 1. Pins

| Image | Tag | Digest seen on the node |
|---|---|---|
| langgenius/dify-api (api, worker, beat) | 1.17.0 | sha256:52be6088dd84… |
| langgenius/dify-web | 1.17.0 | sha256:6a81fcdd82b5… |
| langgenius/dify-plugin-daemon | 0.6.10-local | sha256:0b8f1f1e7668… |
| langgenius/dify-agent-backend | 1.17.0 | sha256:085e097b8d55… |
| langgenius/dify-agent-local-sandbox | 1.17.0 | sha256:316279a82ead… |
| langgenius/dify-sandbox | 0.2.15 | not run (crashes) |
| bitnamilegacy/postgresql, redis (throw-away only) | 15.3.0 / 7.0.11 | not for production |

Full 64-hex digests are to be read from the registry by WP-204 when it pins. Plugin package
`langgenius/openai_api_compatible` **0.0.73**, `.difypkg` sha256
`a3c6524f183083e0f6f57ac50f201700fd019e786bd1971249ef086adcb70008` (546 020 bytes, from
`marketplace.dify.ai/api/v1/plugins/langgenius/openai_api_compatible/0.0.73/download`).
Licence: modified Apache 2.0, one workspace, logo and copyright kept (ADR-0599).

## 2. OpenShift (`restricted-v2`)

| Component | Result | Value WP-204 must set |
|---|---|---|
| api, worker, beat, web, agent-backend | run | `*.podSecurityContext.enabled=false`, `*.containerSecurityContext.enabled=false` (the chart fixes uid 1001/1000 and fsGroup, refused by the SCC) |
| shared storage `api.persistence` | PVC Pending forever | the chart asks **ReadWriteMany**; `gp3-csi` is EBS, RWO only. Use `accessModes: ReadWriteOnce` and a `podAffinity` of the worker on `component: api` (same node), or S3 (`externalS3`) |
| beat | `PermissionError /app/api/storage` | no volume mounted: `OPENDAL_FS_ROOT=/tmp/storage` |
| plugin-daemon | needs writable paths | `PLUGIN_WORKING_PATH=/app/storage/cwd`, `HOME=/app/storage/home`, `UV_CACHE_DIR=/app/storage/uv-cache`, RWO PVC |
| proxy (nginx) | CrashLoop, `mkdir /var/cache/nginx/client_temp` | disable it; use Routes by path (`/console/api`, `/api`, `/v1`, `/files` to api:5001; `/e/` to plugin-daemon:5002; `/` to web:3000: upstream nginx map, not exercised here) |
| sandbox (code node) | CrashLoop, `releaseLibBinary` cannot write | **off** (`sandbox.enabled=false`), ADR-0599 decision 7 |
| local-sandbox (agent) | CrashLoop, `mkdir /home/sandbox` and `/.local` denied | off |
| weaviate | not needed | `weaviate.enabled=false`: Dify starts and answers without any vector store |
| PostgreSQL | the chart wants **two** databases, `dify` and `dify_plugin` (`externalPostgres.database.api/pluginDaemon`) | WP-204 step 2 must create both in `zuno-postgresql` |

## 3. Model provider

- The OpenAI-API-compatible provider is a **plugin**, not built in. Offline install works: upload
  `POST /console/api/workspaces/current/plugin/upload/pkg` (multipart `pkg`), then `.../plugin/install/pkg` with
  `plugin_unique_identifiers`. Login needs the **base64** of the password; cookies `access_token`, `csrf_token`
  (header `X-CSRF-Token`).
- **The install downloads from PyPI**: the daemon runs `uv sync --frozen` per plugin. With the EgressFirewall closed it
  fails. WP-204 must either open `pypi.org` and `files.pythonhosted.org` for the install window, or provide an index
  mirror (`UV_DEFAULT_INDEX`).
- Model registration:
  `POST /console/api/workspaces/current/model-providers/langgenius/openai_api_compatible/openai_api_compatible/models/credentials`
  (not `/models`, which answers `success` and stores nothing). Dify validates by a real call,
  `POST /v1/chat/completions {"model":"auto","max_tokens":5,"messages":[{"role":"user","content":"ping"}]}`, so the
  token proxy must be up before the role configures the provider.
- **What the stub received:** `Authorization: Bearer dummy-key`, `User-Agent: python-requests`, and **no `X-Zuno-*`
  header**. The provider has no custom-header field (credential fields: display_name, api_key, endpoint_url,
  endpoint_model_name, mode, context_size, ...). All `X-Zuno-Agent/Task/Data-Classification` headers therefore come from
  the token proxy (ADR-0601 decision 3).

## 4. MCP tool

`POST /console/api/workspaces/current/tool-provider/mcp`
`{server_url, name, icon, icon_type, icon_background, server_identifier, headers, timeout, sse_read_timeout}`.
Dify speaks streamable HTTP, protocol `2025-06-18`: `POST initialize`, a `GET` with `Accept: text/event-stream` and
`mcp-session-id`, `POST notifications/initialized`, `POST tools/list`. No authorization and no `X-Zuno-*` header: the
proxy adds them. The proxy already relays `GET /mcp` and keeps `mcp-session-id` (tested in WP-202).

## 5. External Knowledge

`POST /console/api/datasets/external-knowledge-api` `{name, settings:{endpoint, api_key}}`. On creation Dify probes
`POST {endpoint}/retrieval` with `Authorization: Bearer <api_key>` and
`{"knowledge_id": "", "query": "", "retrieval_setting": {"top_k": 1, "score_threshold": 0.0}}`, **empty query and id**.
The adapter (WP-205) must answer `200 {"records": []}` to that probe. Real calls expect
`{"records":[{"content","score","title","metadata"}]}`.

## 6. Switches

Settable through the environment (found in `configs/`): `MARKETPLACE_ENABLED=false`, `DISABLE_TELEMETRY=true`,
`ENABLE_CHECK_UPGRADABLE_PLUGIN_TASK=false`, `ENABLE_EMAIL_PASSWORD_LOGIN`, `ENABLE_SOCIAL_OAUTH_LOGIN`,
`CODE_EXECUTION_ENDPOINT` (unset with the sandbox off). **There is no switch to disable datasets or document upload.**
With no vector store and no embedding model only the keyword ("economy") index can work, so the exposure is residual:
ADR-0599 should say "unused and unreachable", not "off". The boot logs showed no outbound URL, but the default is
`MARKETPLACE_ENABLED=true` and `marketplace.dify.ai` is reachable from the cluster.

## 7. Login

Dify Community has e-mail/password login only. Behind oauth2-proxy each person still needs a Dify account. Open
question for the user (WP-204): one shared workspace login following ADR-0595, or per-person accounts.

## 8. Values for WP-204

Spike values: `weaviate.enabled=false`, `proxy.enabled=false`, `sandbox.enabled=false`, `localSandbox.enabled=false`,
security contexts off, RWO volumes, the plugin-daemon and beat environment of section 2.

The scratch namespace is removed at the end of the spike.
