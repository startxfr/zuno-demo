# mcp

Applies `gitops/apps/mcp` (`gitops/charts/mcp-gateway`): the central MCP
Gateway (ADR-0010) that authorizes every tool call against
`policies/tools/tool-policy.yaml` (ADR-0011) before proxying to a
downstream MCP server (`components/mcp-gateway`). CONFIG_SCOPE only — no
separate prepare phase.
