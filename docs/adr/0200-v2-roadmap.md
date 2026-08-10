# v2 roadmap decisions (ADR-0201 – ADR-0209)

- **Status:** Proposed
- **Target:** v2
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

Consolidated from 9 individual ADR files. Each entry below is its own immutable decision record, citable as `ADR-0NNN`; only the Decision line is unique per entry — [Standard clauses](README.md#standard-clauses) (Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution, Related ADRs) apply to every entry unless overridden here.

### ADR-0201: Introduce agent-to-agent communication

Allow approved agent delegation while preserving identity, budget and policy boundaries.

### ADR-0202: Adopt A2A as the inter-agent protocol

Use a standard protocol for agent delegation instead of bespoke point-to-point contracts.

### ADR-0203: Propagate user identity across agent-to-agent calls

Keep authorization grounded in the initiating user during delegated operations.

### ADR-0204: Introduce controlled shared agent memory

Share only approved/promoted knowledge, never raw private conversations by default.

### ADR-0205: Expose agent delegation traces to users

Make delegated actions understandable and auditable in the user experience.

### ADR-0206: Limit recursive agent delegation

Prevent loops and runaway cost through hop/depth and policy limits.

### ADR-0207: Add specialized task-oriented frontend views

Complement chat with structured task-specific interfaces for complex workflows.

### ADR-0208: Automate removal of inaccessible private RAG content

Remove embeddings/content when a user loses source access.

### ADR-0209: Introduce advanced human approval workflows

Pause sensitive operations for explicit approval and resume from persisted checkpoints.
