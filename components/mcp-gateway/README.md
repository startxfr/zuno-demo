# mcp-gateway

Central MCP Gateway (ADR-0010): the single entry point every MCP tool call
in the platform passes through. Authorizes each call using the ADR-0011
policy intersection, then proxies to the right downstream MCP server.

Implementation: FastAPI (Python 3.11), stateless, no database. Deployed by
`ansible/roles/mcp` via `gitops/apps/mcp/application.yaml` ->
`gitops/charts/mcp-gateway` into the shared `zuno-ai` namespace.

## Observability (ADR-0029)

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
- **Body:** a flat JSON object of tool arguments (tool-specific, e.g.
  `{"query": "..."}` for `search_confluence`).
- **Response `200`:**
  ```json
  {
    "tool": "search_confluence",
    "request_id": "…",
    "mcp_server": "confluence-demo",
    "duration_ms": 12.3,
    "result": { "...": "tool-specific payload" }
  }
  ```
- **Response `403`:** `{"detail": "<human-readable reason policy denied the call>"}`
- **Response `401`:** missing/invalid/expired JWT.
- **Response `404`:** unknown tool name.
- **Response `502`:** downstream MCP server unreachable or errored.
- **Response `503`:** the tool policy file is not yet loaded (Track B's
  `policies/tools/tool-policy.yaml` missing or unparsable), or the
  Keycloak JWKS endpoint is unreachable for token validation.

### `GET /healthz` / `GET /readyz`

Liveness always `200`. Readiness returns `503` until `tool-policy.yaml`
has loaded successfully.

### `POST /admin/reload-policy`

Re-reads the policy files from disk without a pod restart - use this if
Track B's policy files land in the image/mount after this pod already
started.

## Tools routed

| Tool | Downstream |
|---|---|
| `get_customer`, `list_open_opportunities`, `get_quote` | proxied to the sales-db MCP server (see Assumption below) |
| `search_confluence`, `list_drive_files`, `read_gmail`, `web_search`, `send_technical_report_email` | demo-mode handlers in `app/handlers/` - see each file's docstring for exactly what changes to call the real API |

Routing is keyed by tool name (a stable, contract-wide constant), not by
the `mcp_server` field in `tool-policy.yaml` - see `app/downstream.py` for
the reasoning.

## Assumption: sales-db MCP server address

`components/mcp-servers/sales-db` is owned by a different track and wasn't
inspectable while this gateway was built. We assume it is reachable
in-cluster as an HTTP+SSE MCP endpoint at
`http://sales-db-mcp.zuno-ai.svc:8000` (override via
`SALES_DB_MCP_URL`), and that `POST {SALES_DB_MCP_URL}/mcp` accepts a
JSON-RPC-style `{"method": "tools/call", "params": {"name": ..., "arguments": ...}}`
body per the MCP `tools/call` shape, forwarding the caller's Bearer JWT.
If the real server instead exposes MCP-over-stdio via a sidecar, or a
different HTTP shape, only `app/downstream.py:_invoke_sales_db` needs to
change - reconcile this once that track's implementation lands.

## ADR-0011 intersection: what this gateway does and does not check

This gateway authoritatively enforces:

1. the tool exists in `policies/tools/tool-policy.yaml`;
2. the request's declared `X-Zuno-Data-Classification` meets the tool's
   `min_classification`;
3. the caller's JWT `groups` intersect the tool's `allowed_groups`.

It does **not** independently re-verify the agent's OKF tool declaration or
the current task's declared rights - those are the Agent Runtime's
responsibility (it should only ever call a tool its OKF/task actually
grants). Track E has not authored per-agent OKF tool declarations yet
(`agents/tekos/tasks`, `agents/tekos/tools` are still stubs); adding a
second, independent check here once those exist is a tracked v1 hardening
item, not a v0 regression.

## Local development

```bash
# from the repository root
docker build -f components/mcp-gateway/Dockerfile -t zuno/mcp-gateway:local .
docker run -p 8080:8080 \
  -e KEYCLOAK_ISSUER=https://keycloak-zuno.apps.example.com/realms/zuno \
  zuno/mcp-gateway:local
```

Configuration is entirely through environment variables - see
`app/auth.py`, `app/policy.py` and `app/downstream.py` for the full list
and their defaults. No secret is ever hardcoded (ADR-0024); this service
does not currently need a Vault-backed credential of its own (JWT
validation only needs the public JWKS endpoint), but downstream API keys
for the real (non-demo) Confluence/Drive/Gmail/web-search integrations
would follow the same `secret/zuno/providers/<name>` + `ExternalSecret`
pattern used by `ansible/roles/llm` once those integrations are built.
