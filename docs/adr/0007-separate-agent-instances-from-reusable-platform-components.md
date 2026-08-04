# ADR-0007: Separate agent instances from reusable platform components

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

## Context

Zuno Demo requires an explicit, reviewable architecture decision so implementation, security and roadmap work remain aligned across the MVP and future releases.

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

## Alternatives considered

Alternatives remain valid when documented in implementation discussions, but this ADR records the selected direction for the stated target release.

## Consequences

Implementation and documentation must follow this decision. Any material change requires a superseding ADR and an explicit migration/evolution note.

## Security considerations

Security implications must be evaluated during implementation. This decision must not weaken identity propagation, data classification, least privilege, secret management or auditability.

## Operational considerations

Operational checks, observability and rollback/diagnostic procedures must be added as the corresponding capability becomes executable.

## Migration / evolution

Future changes must be documented by a new ADR using `Supersedes ADR-0007` when applicable.

## Related ADRs

See [ADR index](README.md).
