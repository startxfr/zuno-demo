# MCP server: salesforce

Comage's live Salesforce integration (ADR-0326/WP-33). Real, live access to
Salesforce Opportunities through the three capabilities ADR-0326 names for
Comage: `salesforce.opportunity.read`, `salesforce.opportunity.create`,
`salesforce.opportunity.update` - exposed here as `read_opportunity`,
`create_opportunity`, `update_opportunity` (the MCP Gateway's binding
registry, `platform/bindings/tools/tool-bindings.yaml`, maps the logical
capability ID to whichever tool name this server actually exposes).

Transport: a real, standards-compliant MCP server - the official `mcp`
Python SDK's `MCPServer`, streamable-HTTP transport, mounted at `POST
/mcp` - same shape as `components/mcp-servers/confluence`, which this
server is templated from. The gateway remains the trust boundary; this
server does not re-validate the caller's end-user JWT, since the
gateway's policy intersection already happened before this server is ever
reached.

Network location (`gitops/charts/mcp-salesforce`'s `NetworkPolicy`,
restricting ingress to the gateway's pods specifically) is not the only
control. Every `POST /mcp` call must also carry `X-Zuno-Gateway-Token`, a
shared secret only the gateway holds (same pattern as confluence/sales-db).

**Authentication mode: `service-identity`.** Every call to Salesforce uses
one shared technical connected-app identity - a pre-issued OAuth2 bearer
access token (the standard Salesforce REST API convention), sourced from
an `ExternalSecret` resolving `zuno/salesforce/technical` (`url`/
`access_token` keys, seeded by `ansible/roles/vault/tasks/install.yml`).
This server has no per-user Salesforce identity to check; the MCP
Gateway's `policy.evaluate()` authorizes the caller's agent/task/role/
classification *before* this shared identity is ever used. Refreshing an
expired token is an operator/Vault-rotation concern outside this server's
scope - no real Salesforce org is wired in this demo.

**Retrieval behavior**: ordinary deal-status questions are answered from
`knowledge.sales` (already-ingested Salesforce content, WP-22), unchanged
by this server. These live tools are for freshness-sensitive reads (a
mutable field's CURRENT value) and any write - not a second, parallel
read path for ordinary questions (ADR-0205).

`knowledge.sales`/`salesforce.*` are strictly separate from
`knowledge.sxa-legacy`/`sxa.*` in both directions (ADR-0206) - this server
never touches the legacy SXA snapshot (`components/mcp-servers/sales-db`).

`GET /healthz` checks that `SALESFORCE_BASE_URL`/`SALESFORCE_ACCESS_TOKEN`
are configured; it deliberately does **not** make a live Salesforce call
on every probe, same reasoning as confluence's own healthz.

See `server.py`, `Dockerfile`, `requirements.txt`,
`tests/test_mcp_protocol.py` (exercises the real MCP SDK client against
this server's ASGI app, with Salesforce itself mocked). Deployed by
`gitops/charts/mcp-salesforce` in the `zuno-ai-run` namespace, matching
`components/mcp-gateway`'s binding registry endpoint
(`http://salesforce-mcp.zuno-ai-run.svc:8000`).
