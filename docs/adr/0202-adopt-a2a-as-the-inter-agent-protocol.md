# ADR-0202: Adopt A2A as the inter-agent protocol

- **Status:** Proposed
- **Target:** v2
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

## Context

Zuno Demo requires an explicit, reviewable architecture decision so implementation, security and roadmap work remain aligned across the MVP and future releases.

## Decision

Use a standard protocol for agent delegation instead of bespoke point-to-point contracts.

## Alternatives considered

Alternatives remain valid when documented in implementation discussions, but this ADR records the selected direction for the stated target release.

## Consequences

Implementation and documentation must follow this decision. Any material change requires a superseding ADR and an explicit migration/evolution note.

## Security considerations

Security implications must be evaluated during implementation. This decision must not weaken identity propagation, data classification, least privilege, secret management or auditability.

## Operational considerations

Operational checks, observability and rollback/diagnostic procedures must be added as the corresponding capability becomes executable.

## Migration / evolution

Future changes must be documented by a new ADR using `Supersedes ADR-0202` when applicable.

## Related ADRs

See [ADR index](README.md).
