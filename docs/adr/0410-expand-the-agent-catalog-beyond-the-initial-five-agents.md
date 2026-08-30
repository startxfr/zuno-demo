# ADR-0410: Expand the agent catalog beyond the initial five agents

- **Status:** Proposed (deferred - WP-41 cancelled 2026-08-23; the merged Naveo agent bundle under `agents/naveo/` remains in the repo but the sixth-agent deployment gate is not being pursued)
- **Target:** v0.7 (retargeted from v0.4 on 2026-08-30 — WP-41 cancelled, no live pursuit planned; deprioritized alongside ADR-0111/ADR-0115/ADR-0352 in v0.7's long-term/harder band rather than v0.4, which is otherwise fully closed)
- **Date:** 2026-08-15
- **Decision owners:** Zuno Demo architecture team
- **Renumbered:** formerly ADR-0306 (2026-08-15 move to the v0.4 stream)

## Decision

Demonstrate that the generic platform supports broader enterprise agent
onboarding (the stub decision, promoted verbatim from
`docs/roadmap/adr-decisions-v0.3.md`).

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
