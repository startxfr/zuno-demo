# MCP server: sales-db

Controlled deterministic access to the migrated SXA sales database, including validated state transitions.

Three tools, each a parameterized, read-only query against the schema in
`data/sxa/schema/001_init.sql` - never LLM-constructed SQL (ADR-0017):
`get_customer(customer_id)`, `list_open_opportunities(owner?)`,
`get_quote(quote_id)`.

Transport: plain JSON-RPC 2.0 over `POST /mcp`
(`{"method": "tools/call", "params": {"name", "arguments"}}` ->
`{"result": ...}` or `{"error": {...}}`), matched exactly against
`components/mcp-gateway`'s documented assumption
(`app/downstream.py:_invoke_sales_db`) - the gateway is the only caller and
the trust boundary; this server does not re-validate the caller's JWT.

DB credentials (`PGUSER`/`PGPASSWORD`) come from an `ExternalSecret`
resolving `secret/zuno/postgresql/app` (seeded by `ansible/roles/vault`) -
never hardcoded, per ADR-0024. See `server.py`, `Dockerfile`,
`requirements.txt`. Deployed alongside the rest of the data layer by
`ansible/roles/sql_schema`'s GitOps Application, in the `zuno-platform`
namespace (matching `components/mcp-gateway`'s `salesDbMcpUrl` assumption:
`http://sales-db-mcp.zuno-platform.svc:8000`).
