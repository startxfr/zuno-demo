# ADR-0023: Use a namespace-per-agent isolation model

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

## Decision

Separate each agent instance with dedicated namespaces, service accounts, quotas and NetworkPolicies.

**Implementation status (2026-08-04):** each agent instance's namespace
follows the `zuno-agent-<agent>` naming convention (`zuno-agent-tekos`,
`zuno-agent-comage`, `zuno-agent-advantage`, `zuno-agent-finage`,
`zuno-agent-arkos` - `gitops/charts/namespaces/values.yaml`), so the family
reads clearly alongside the functional-domain namespaces from
[ADR-0007](0007-separate-agent-instances-from-reusable-platform-components.md)
(`zuno-auth`/`zuno-ai`/`zuno-data`/`zuno-monitoring`). Only `zuno-agent-tekos`
hosts a real workload in v0; the default-deny-other-namespaces
`NetworkPolicy` and per-namespace `ResourceQuota` this ADR calls for are
unchanged in shape, just renamed with their namespace.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution and Related ADRs.
