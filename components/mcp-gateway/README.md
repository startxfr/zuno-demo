# mcp-gateway

Central MCP Gateway: the single entry point every MCP tool call
in the platform passes through. Authorizes each call using the
policy intersection, then proxies to the right downstream MCP server.

Implementation: FastAPI (Python 3.11), stateless, no database. Deployed by
`ansible/roles/mcp` via `gitops/apps/mcp/application-d1.yaml` ->
`gitops/charts/mcp-gateway` into the shared `zuno-ai-run` namespace.

## Observability

`app/telemetry.py` initializes an OTLP tracer/meter at startup and wraps
every `/v1/tools/{tool}/invoke` call in a `tool_invoke` span (tool, caller
classification, latency, and a precise outcome - `allowed`, `denied`,
`unknown_tool`, `bad_request`, `downstream_error`, or `error`) plus the
`zuno.tool_invocations` counter.

## HTTP API contract

### `POST /v1/tools/{tool_name}/invoke`

- **Auth:** `Authorization: Bearer <keycloak-jwt>` (required). Validated
  against the realm's JWKS endpoint; the token's `groups` claim drives
  authorization.
- **Header:** `X-Zuno-Data-Classification: C1|C2|C3` (optional, default
  `C1`) - the caller's declared classification ceiling for this request.
  Compared against the tool's `min_classification` from
  `policies/tools/tool-policy.yaml`.
- **Headers:** `X-Zuno-Agent`, `X-Zuno-Task` (both required) - which
  OKF-defined agent and task (`agents/<agent>/agent.okf.md` /
  `tasks/<task>.md`) is making this call. Missing, unknown, or a
  tool absent from that agent/task's declaration all deny the call - the
  gateway fails closed on any invalid policy input.
- **Body:** a flat JSON object of tool arguments (tool-specific, e.g.
  `{"query": "..."}` for `search_confluence`).
- **Response `200`:**
  ```json
  {
    "tool": "search_confluence",
    "capability": "confluence.page.search",
    "binding": "confluence",
    "request_id": "…",
    "mcp_server": "confluence",
    "duration_ms": 12.3,
    "external_model_policy": { "allow_context": false },
    "result": { "...": "tool-specific payload" }
  }
  ```
  `external_model_policy.allow_context` mirrors the tool's
  `external_model_policy.allow_context` in `tool-policy.yaml` (default
  `true`) - `false` means this result must only be processed by local
  inference regardless of the classification-driven SaaS-eligibility that
  would otherwise apply. The caller (Agent Runtime) is expected to set
  `X-Zuno-Local-Only: true` on its own downstream model call when this is
  `false`.
- **Response `403`:** `{"detail": "<human-readable reason policy denied the call>"}`
- **Response `401`:** missing/invalid/expired JWT.
- **Response `404`:** unknown tool name.
- **Response `502`:** downstream MCP server unreachable or errored.
- **Response `503`:** the tool policy file or the `agents/` OKF bundles are
  not yet loaded (missing or unparsable), or the Keycloak JWKS endpoint is
  unreachable for token validation.

### `GET /healthz` / `GET /readyz`

Liveness always `200`. Readiness returns `503` until both
`tool-policy.yaml` and every `agents/<name>/agent.okf.md` bundle have
loaded successfully.

### `POST /admin/reload-policy`

Re-reads the policy files and the `agents/` OKF bundles from disk without
a pod restart - use this if Track B's policy files or an agent definition
land in the image/mount after this pod already started.

## Tools routed

| Tool | Downstream |
|---|---|
| `confluence.page.search` (alias `search_confluence`), `confluence.page.read`, `confluence.page.create`, `confluence.page.update` | proxied to the confluence MCP server (see below) |
| `list_drive_files`, `read_gmail`, `web_search`, `send_technical_report_email` | demo-mode handlers in `app/handlers/` - see each file's docstring for exactly what changes to call the real API |

Routing: the caller's tool name (canonical
`<domain>.<resource>.<verb>` capability ID, or a legacy alias kept during
migration) is resolved through the platform backend-binding registry
(`platform/bindings/tools/tool-bindings.yaml`, loaded by
`app/bindings.py`) - not through hard-coded tool-name sets. An unknown
name or missing binding fails closed before any backend is contacted, and
startup/readiness validation requires every policy-listed name to resolve
to exactly one binding.

## Downstream MCP servers: real standards-compliant MCP protocol

`components/mcp-servers/confluence`, `/salesforce` and `/git-forge` each
speak a real, standards-compliant MCP server (the official `mcp` Python
SDK, streamable-HTTP transport, mounted at `/mcp`).
`app/downstream.py:_invoke_streamable_http` uses the SDK's own
`mcp.client.session.ClientSession` +
`mcp.client.streamable_http.streamable_http_client` (a real `initialize`
handshake, then `tools/call`) against e.g.
`http://confluence-mcp.zuno-ai-run.svc:8000/mcp` (override the host/port
via `CONFLUENCE_MCP_URL`), forwarding the caller's Bearer JWT for
audit/observability (the downstream server doesn't itself re-validate it -
the gateway's own policy intersection already happened). Each endpoint
comes from that capability's `endpoint` block in the binding registry.

The two other MCP servers named in `tool-policy.yaml`'s `mcp_server`
field (`google-workspace`, `web-search`) have no real
implementation yet - `components/mcp-servers/<name>/` is a one-line
README each; their traffic is still served by this gateway's own
`app/handlers/*.py` demo-mode functions. `confluence` was the second
real migration (see below).

## Confluence MCP server: first real external integration

`components/mcp-servers/confluence` speaks the real MCP protocol described
above and fronts a real *external* API (Confluence Cloud) rather than an
internal database - Zuno's first working example of the full
target chain: Agent Runtime -> this gateway -> logical capability ->
backend binding -> real MCP server -> external API. Replaces
`app/handlers/confluence.py`'s demo-mode handler (deleted); the four
capabilities already named (`confluence.page.search/read/create/
update`) route through `_invoke_streamable_http`, resolved via their
`platform/bindings/tools/tool-bindings.yaml`
entries (`endpoint.default: http://confluence-mcp.zuno-ai-run.svc:8000`).

Authentication mode is `service-identity`: the server itself holds one
shared Confluence technical identity (`zuno/confluence/technical` in
Vault - email + API token); this gateway's own policy intersection is
what authorizes the *caller*, before that shared identity is ever used -
see `components/mcp-servers/confluence/README.md` for details.

A tool function's structured-content result gets wrapped by the SDK as
`{"result": <value>}` when its return type is a plain `Dict[str, Any]`
(MCP requires an object-typed top-level schema for structured content,
and a bare dict return has none) - `_invoke_streamable_http` unwraps that
single-key envelope so callers keep seeing the original
original shape. See `tests/test_downstream_streamable_http.py` for a
local MCP server fixture that reproduces this behavior.

`_invoke_streamable_http` also sends `X-Zuno-Gateway-Token`
(`MCP_GATEWAY_WORKLOAD_TOKEN` env var, sourced from an `ExternalSecret`
resolving `zuno/mcp/gateway-workload-token` - vault-generated by
`ansible/roles/vault/tasks/install.yml`) on every call - a
workload-identity proof every downstream server validates in addition to
its NetworkPolicy boundary (e.g. `gitops/charts/mcp-confluence`), since
agent-runtime and the MCP servers share the `zuno-ai-run` namespace and a
direct agent-runtime-to-MCP-server path must be forbidden.

## Policy intersection: all five factors

This gateway authoritatively enforces the full intersection - any single
"no" is a "no", evaluated in this order:

1. **agent_declaration** - the calling agent (`X-Zuno-Agent`)'s
   `agents/<agent>/agent.okf.md` bundle declares this tool under at least
   one of its tasks (`app/agent_declarations.py`).
2. **task_rights** - the calling task (`X-Zuno-Task`)'s
   `agents/<agent>/tasks/<task>.md` `zuno.allowed_tools` includes this
   tool - a task can only narrow, never widen, its agent's own
   declaration.
3. the tool exists in `policies/tools/tool-policy.yaml`;
4. the request's declared `X-Zuno-Data-Classification` meets the tool's
   `min_classification`;
5. **user_group_rights** - the caller's JWT `groups` intersect the tool's
   `allowed_groups`.

## Local development

```bash
# from the repository root
docker build -f components/mcp-gateway/Dockerfile -t zuno/mcp-gateway:local .
docker run -p 8080:8080 \
  -e KEYCLOAK_ISSUER=https://keycloak-zuno.apps.mycluster.example.com/realms/zuno \
  zuno/mcp-gateway:local
```

Configuration is entirely through environment variables - see
`app/auth.py`, `app/policy.py`, `app/bindings.py` and `app/downstream.py`
for the full list and their defaults. No secret is ever hardcoded;
this gateway itself does not need a Vault-backed credential of
its own (JWT validation only needs the public JWKS endpoint) and never
sees downstream API keys - those live only in the backend MCP server that
owns each integration (e.g. `components/mcp-servers/confluence`'s own
`zuno/confluence/technical` secret). The remaining demo-mode integrations
(Drive/Gmail/web-search) would follow the same real-MCP-server pattern
confluence and salesforce already established, with credentials via the
same `zuno/<provider>/...` + `ExternalSecret` convention.
