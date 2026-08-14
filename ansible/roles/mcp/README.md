# mcp

Applies `gitops/apps/mcp` (`gitops/charts/mcp-gateway`): the central MCP
Gateway (ADR-0010) that authorizes every tool call against
`policies/tools/tool-policy.yaml` (ADR-0011) before proxying to a
downstream MCP server (`components/mcp-gateway`). A Day 1 component
(ADR-0056) with a documented no-op `install.yml` - no operator dependency
of its own.

Also applies `gitops/apps/mcp-confluence` (`gitops/charts/mcp-confluence`,
ADR-0117): the real Confluence Cloud MCP server, under this same run
component - same name-mismatch self-sufficiency pattern
`ansible/roles/sql_schema` uses for `gitops/apps/mcp-sales-db`. Both
images (`mcp-gateway`, `mcp-confluence`) build via the `mcp_build` Day 1
build component (`make d1 build mcp`).
