# datascience

`prepare.yml` creates the `zuno-ai` namespace the `models` role's
`InferenceService` deploys into (labeled for the RHOAI dashboard), shared
with the rest of the AI/agent-serving stack (ai-gateway, agent-runtime,
mcp-gateway, mcp-sales-db). `configure.yml` applies a `ResourceQuota`
capping GPU consumption at 1 - this demo has exactly one 24GB L4 budgeted
for the single local model. Depends on `openshift_ai` (`DataScienceCluster`
Ready) having run first.
