# mcp-gateway

Central MCP Gateway (ADR-0010): the single entry point every MCP tool call
in the platform passes through. Authorizes each call using the ADR-0011
policy intersection, then proxies to the right downstream MCP server.

Implementation: FastAPI (Python 3.11), stateless, no database. Deployed by
`ansible/roles/mcp` via `gitops/apps/mcp/application-d1.yaml` ->
`gitops/charts/mcp-gateway` into the shared `zuno-ai-run` namespace.

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
- **Headers:** `X-Zuno-Agent`, `X-Zuno-Task` (both required, ADR-0036) -
  which OKF-defined agent and task (`agents/<agent>/agent.okf.md` /
  `tasks/<task>.md`, ADR-0038) is making this call. Missing, unknown, or a
  tool absent from that agent/task's declaration all deny the call - the
  gateway fails closed on any invalid policy input, per this ADR's
  Security considerations.
- **Body:** a flat JSON object of tool arguments (tool-specific, e.g.
  `{"query": "..."}` for `search_confluence`).
- **Response `200`:**
  ```json
  {
    "tool": "search_confluence",
    "request_id": "…",
    "mcp_server": "confluence-demo",
    "duration_ms": 12.3,
    "external_model_policy": { "allow_context": false },
    "result": { "...": "tool-specific payload" }
  }
  ```
  `external_model_policy.allow_context` (ADR-0035) mirrors the tool's
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
| `get_customer`, `list_open_opportunities`, `get_quote` | proxied to the sales-db MCP server (see Assumption below) |
| `search_confluence`, `list_drive_files`, `read_gmail`, `web_search`, `send_technical_report_email` | demo-mode handlers in `app/handlers/` - see each file's docstring for exactly what changes to call the real API |

Routing is keyed by tool name (a stable, contract-wide constant), not by
the `mcp_server` field in `tool-policy.yaml` - see `app/downstream.py` for
the reasoning.

## Sales-db MCP server: real standards-compliant MCP protocol (ADR-0043)

Reconciled: `components/mcp-servers/sales-db` speaks a real, standards-
compliant MCP server (the official `mcp` Python SDK, streamable-HTTP
transport, mounted at `/mcp`) as of ADR-0043 - not the hand-rolled
JSON-RPC-shaped endpoint this section used to describe as an assumption.
`app/downstream.py:_invoke_sales_db` uses the SDK's own
`mcp.client.session.ClientSession` +
`mcp.client.streamable_http.streamable_http_client` (a real `initialize`
handshake, then `tools/call`) against
`http://sales-db-mcp.zuno-ai-run.svc:8000/mcp` (override the host/port
via `SALES_DB_MCP_URL`), forwarding the caller's Bearer JWT for
audit/observability (sales-db doesn't itself re-validate it - the
gateway's own ADR-0011 policy intersection already happened) - exactly as
this module's own docstring anticipated before the migration: "only
`_invoke_sales_db` needs to change."

The four other MCP servers named in `tool-policy.yaml`'s `mcp_server`
field (`confluence`, `google-workspace`, `lucidchart`, `web-search`) have
no real implementation yet - `components/mcp-servers/<name>/` is a
one-line README each - so there is nothing to migrate for them; their
traffic is still served by this gateway's own `app/handlers/*.py`
demo-mode functions. "Migrate servers incrementally" (ADR-0043's
Operational considerations) means sales-db is the first and, as of this
change, only real migration.

**Verified against the real SDK, not just this module's own code**: a
tool function's structured-content result gets wrapped by the SDK as
`{"result": <value>}` when its return type is a plain `Dict[str, Any]`
(MCP requires an object-typed top-level schema for structured content,
and a bare dict return has none) - `_invoke_sales_db` unwraps that
single-key envelope so callers keep seeing the pre-migration
`{"customer": ..., "contacts": ...}` shape exactly. See
`tests/test_downstream_sales_db.py` for a from-scratch local MCP server
fixture that reproduces and locks in this behavior.

**ADR-0037**: `_invoke_sales_db` also sends `X-Zuno-Gateway-Token`
(`MCP_GATEWAY_WORKLOAD_TOKEN` env var, sourced from an `ExternalSecret`
resolving `zuno/mcp/gateway-workload-token` - vault-generated by
`ansible/roles/vault/tasks/install.yml`) on every call - a
workload-identity proof `components/mcp-servers/sales-db` validates in
addition to the NetworkPolicy boundary (`gitops/charts/mcp-sales-db`),
since a direct agent-runtime-to-MCP-server path must be forbidden even
though agent-runtime and sales-db-mcp share the `zuno-ai-run` namespace.

## ADR-0011 intersection: all five factors (ADR-0036)

This gateway authoritatively enforces the full intersection - any single
"no" is a "no", evaluated in this order:

1. **agent_declaration** - the calling agent (`X-Zuno-Agent`)'s
   `agents/<agent>/agent.okf.md` bundle (ADR-0038) declares this tool
   under at least one of its tasks (`app/agent_declarations.py`).
2. **task_rights** - the calling task (`X-Zuno-Task`)'s
   `agents/<agent>/tasks/<task>.md` `zuno.allowed_tools` includes this
   tool - a task can only narrow, never widen, its agent's own
   declaration.
3. the tool exists in `policies/tools/tool-policy.yaml`;
4. the request's declared `X-Zuno-Data-Classification` meets the tool's
   `min_classification`;
5. **user_group_rights** - the caller's JWT `groups` intersect the tool's
   `allowed_groups`.

Before ADR-0036, only factors 3-5 were checked here (1-2 were deferred as
"Track E has not authored per-agent OKF tool declarations yet" - true at
the time, no longer true once ADR-0038 landed). Fixing this also surfaced
and fixed a real, unrelated pre-existing bug: `PolicyStore.reload()` was
iterating `tool-policy.yaml`'s raw parsed dict directly instead of its
`tools:` list, so every real load of that file raised `TypeError` and every
tool call failed closed - this had gone uncaught because no test exercised
`PolicyStore.reload()` itself (`evaluations/tekos/security_checks.py`'s
config-consistency check parses the same file independently, which is why
it never caught the loader bug).

## Local development

```bash
# from the repository root
docker build -f components/mcp-gateway/Dockerfile -t zuno/mcp-gateway:local .
docker run -p 8080:8080 \
  -e KEYCLOAK_ISSUER=https://keycloak-zuno.apps.mycluster.example.com/realms/zuno \
  zuno/mcp-gateway:local
```

Configuration is entirely through environment variables - see
`app/auth.py`, `app/policy.py` and `app/downstream.py` for the full list
and their defaults. No secret is ever hardcoded (ADR-0024); this service
does not currently need a Vault-backed credential of its own (JWT
validation only needs the public JWKS endpoint), but downstream API keys
for the real (non-demo) Confluence/Drive/Gmail/web-search integrations
would follow the same `zuno/providers/<name>` + `ExternalSecret`
pattern used by `ansible/roles/llm` once those integrations are built.
