# mcp

Applies `gitops/apps/mcp` (`gitops/charts/mcp-gateway`): the central MCP
Gateway (ADR-0010) that authorizes every tool call against
`policies/tools/tool-policy.yaml` (ADR-0011) before proxying to a
downstream MCP server (`components/mcp-gateway`). A Day 1 component
(ADR-0056) with a documented no-op `install.yml` - no operator dependency
of its own.

Also applies `gitops/apps/mcp-confluence` (`gitops/charts/mcp-confluence`,
ADR-0117), `gitops/apps/mcp-salesforce` (`gitops/charts/mcp-salesforce`,
ADR-0326/WP-33) and `gitops/apps/mcp-git-forge` (`gitops/charts/mcp-git-forge`,
ADR-0120/WP-058): the real Confluence Cloud, Salesforce Opportunity and
GitHub/GitLab MCP servers, under this same run component - same
name-mismatch self-sufficiency pattern this role uses throughout. All four
images (`mcp-gateway`,
`mcp-confluence`, `mcp-salesforce`, `mcp-git-forge`) build via the
`mcp_build` Day 1 build component (`make d1 build mcp`).
