# ADR-0306: Expand the agent catalog beyond the initial five agents

- **Status:** Partially implemented (template, validation workflow and sixth-agent definition merged; deployment gate pending)
- **Target:** v0.3
- **Date:** 2026-08-15
- **Decision owners:** Zuno Demo architecture team

## Decision

Demonstrate that the generic platform supports broader enterprise agent
onboarding (the stub decision, promoted verbatim from
`docs/adr/0300-v0.3-roadmap.md`).

Prove ADR-0307's path by onboarding a sixth demo agent (synthetic
persona, existing knowledge domains and capabilities only, no new
external systems) end to end: template scaffold → validation workflow →
review → deployment via `AIAgent` CR → evaluation gate. The sixth agent
is a permanent template regression proof.

See [Standard clauses](README.md#standard-clauses) for Context,
Alternatives, Consequences, Security/Operational considerations,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0307](0307-support-self-service-agent-onboarding.md)
- [ADR-0326](0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md)
