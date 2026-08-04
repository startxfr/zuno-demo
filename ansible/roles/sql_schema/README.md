# sql_schema

Applies the SXA-derived schema and synthetic fixtures (`data/sxa/`,
ADR-0016, ADR-0025) via a one-shot Kubernetes `Job` running `psql`, then
applies the sales-db MCP server (ADR-0017,
`gitops/apps/mcp-sales-db` → `gitops/charts/mcp-sales-db` →
`components/mcp-servers/sales-db`) as a GitOps Application. The schema
apply is imperative (not a standing GitOps app — nothing is "declaratively
running" about a migration once it has run); the MCP server is a real
workload, so it gets the standard Application treatment. Depends on
`postgresql` having run first.
