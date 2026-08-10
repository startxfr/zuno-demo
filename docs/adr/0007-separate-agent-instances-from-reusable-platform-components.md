# ADR-0007: Separate agent instances from reusable platform components

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

## Decision

Implement generic platform services once and instantiate agents through declarative configuration.

**Implementation status (2026-08-04):** the shared platform services this
ADR describes are grouped into namespaces by functional domain rather than
one catch-all namespace: `zuno-auth` (Keycloak), `zuno-ai` (ai-gateway,
agent-runtime, mcp-gateway, mcp-sales-db, models/KServe - the AI/agent-
serving stack), `zuno-data` (PostgreSQL, Vault, rag-service, the SXA
schema/fixtures Job) and `zuno-telemetry` (the shared OTel Collector). This
reflects a deliberate choice to group by what a component *is* rather than
scatter everything into a single namespace or, at the other extreme, give
every platform service its own namespace - see [ADR-0023](0023-use-a-namespace-per-agent-isolation-model.md)
for the equivalent per-agent-instance layout.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution and Related ADRs.
