# MCP server: confluence

Zuno's first real external MCP integration. Real, live access to
Confluence Cloud through the four capabilities already named:
`confluence.page.search`, `confluence.page.read`, `confluence.page.create`,
`confluence.page.update` - exposed here as `search_pages`, `read_page`,
`create_page`, `update_page` (the MCP Gateway's binding registry,
`platform/bindings/tools/tool-bindings.yaml`, maps the logical capability
ID to whichever tool name this server actually exposes).

Transport: a real, standards-compliant MCP server - the
official `mcp` Python SDK's `MCPServer`, streamable-HTTP transport, mounted
at `POST /mcp` - same shape as `components/mcp-servers/sales-db`. The
gateway remains the trust boundary; this server does not re-validate the
caller's end-user JWT, since the gateway's policy intersection already
happened before this server is ever reached.

Network location (`gitops/charts/mcp-confluence`'s
`NetworkPolicy`, restricting ingress to the gateway's pods specifically)
is not the only control. Every `POST /mcp` call must also carry
`X-Zuno-Gateway-Token`, a shared secret only the gateway holds (same
pattern as sales-db).

**Authentication mode: `service-identity`.** Every call to
Confluence uses one shared technical identity - email + API token, HTTP
Basic Auth (the standard Atlassian Cloud REST API convention, matching
`components/rag-ingestion`'s own `_confluence_auth`) - sourced from an
`ExternalSecret` resolving `zuno/confluence/technical` (`url`/`email`/
`token` keys, seeded by `ansible/roles/vault/tasks/install.yml`). This
server has no per-user Confluence identity to check; the MCP Gateway's
`policy.evaluate()` authorizes the caller's agent/task/role/classification
*before* this shared identity is ever used.

**Retrieval behavior**: normal technical questions are answered
from `knowledge.tech` (already-ingested Confluence content),
unchanged by this server. These live tools are for freshness-sensitive
reads and any write - not a second, parallel read path for ordinary
questions.

`GET /healthz` checks that `CONFLUENCE_BASE_URL`/`CONFLUENCE_EMAIL`/
`CONFLUENCE_API_TOKEN` are configured; it deliberately does **not** make a
live Confluence call on every probe (unlike sales-db's healthz, which does
a free local DB round-trip) - a Kubernetes liveness/readiness probe firing
every ~10-15s against a real external SaaS API would be a needless,
avoidable load/quota cost.

See `server.py`, `Dockerfile`, `requirements.txt`, `tests/test_mcp_protocol.py`
(exercises the real MCP SDK client against this server's ASGI app, with
Confluence itself mocked). Deployed by `gitops/charts/mcp-confluence` in the
`zuno-ai-run` namespace, matching `components/mcp-gateway`'s binding
registry endpoint (`http://confluence-mcp.zuno-ai-run.svc:8000`).
