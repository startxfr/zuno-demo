# ADR-0023: Use a namespace-per-agent isolation model

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

## Context

Zuno Demo requires an explicit, reviewable architecture decision so implementation, security and roadmap work remain aligned across the MVP and future releases.

## Decision

Separate each agent instance with dedicated namespaces, service accounts, quotas and NetworkPolicies.

**Implementation status (2026-08-04):** each agent instance's namespace
follows the `zuno-agent-<agent>` naming convention (`zuno-agent-tekos`,
`zuno-agent-comage`, `zuno-agent-advantage`, `zuno-agent-finage`,
`zuno-agent-arkos` - `gitops/charts/namespaces/values.yaml`), so the family
reads clearly alongside the functional-domain namespaces from
[ADR-0007](0007-separate-agent-instances-from-reusable-platform-components.md)
(`zuno-auth`/`zuno-ai`/`zuno-data`/`zuno-telemetry`). Only `zuno-agent-tekos`
hosts a real workload in v0; the default-deny-other-namespaces
`NetworkPolicy` and per-namespace `ResourceQuota` this ADR calls for are
unchanged in shape, just renamed with their namespace.

## Alternatives considered

Alternatives remain valid when documented in implementation discussions, but this ADR records the selected direction for the stated target release.

## Consequences

Implementation and documentation must follow this decision. Any material change requires a superseding ADR and an explicit migration/evolution note.

## Security considerations

Security implications must be evaluated during implementation. This decision must not weaken identity propagation, data classification, least privilege, secret management or auditability.

## Operational considerations

Operational checks, observability and rollback/diagnostic procedures must be added as the corresponding capability becomes executable.

## Migration / evolution

Future changes must be documented by a new ADR using `Supersedes ADR-0023` when applicable.

## Related ADRs

See [ADR index](README.md).
