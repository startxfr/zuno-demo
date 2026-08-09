# sql_schema

Builds the `zuno-sxa-schema` ConfigMap (`data/sxa/`, ADR-0016, ADR-0025)
and applies the Namespace, then registers two GitOps Applications:
`zuno-mcp-sales-db-d0` (`gitops/charts/sql-schema` - a `PreSync` hook `Job`
running `psql` against that ConfigMap, plus the PostgreSQL credentials
`ExternalSecret` it needs) and `zuno-mcp-sales-db-d1` (`gitops/charts/
mcp-sales-db` → `components/mcp-servers/sales-db`, the sales-db MCP server
itself, ADR-0017). ArgoCD blocks `-d0` `Synced` until the hook Job
succeeds, so `-d1` never syncs before the schema exists (ADR-0313 - the
schema apply used to be an ansible-managed `Job`, not a GitOps
Application). Depends on `postgresql` having run first.
