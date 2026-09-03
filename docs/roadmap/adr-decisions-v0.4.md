# v0.4 roadmap decisions (ADR-0401 – ADR-0409)

- **Status:** Proposed
- **Target:** v0.4
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team

Consolidated from 9 individual ADR files. Each entry below is its own immutable decision record, citable as `ADR-0NNN`; only the Decision line is unique per entry - [Standard clauses](README.md#standard-clauses) (Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution, Related ADRs) apply to every entry unless overridden here.

These nine decisions were originally drafted as ADR-0201–0209 under the v0.2 roadmap. They moved here because agent-to-agent (A2A) delegation and cross-agent shared memory are only meaningful once multiple agents actually exist to delegate to and share with - that is a v0.3 outcome (see [ADR-0326](../adr/0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md)). v0.2 is scoped to maturing the single-agent (Tekos) MCP/RAG/model-routing pattern; v0.4 is where that pattern is extended across agents through delegation.

### ADR-0401: Introduce agent-to-agent communication

Allow approved agent delegation while preserving identity, budget and policy boundaries.

### ADR-0402: Adopt A2A as the inter-agent protocol

Use a standard protocol for agent delegation instead of bespoke point-to-point contracts.

### ADR-0403: Propagate user identity across agent-to-agent calls

Keep authorization grounded in the initiating user during delegated operations.

### ADR-0404: Introduce controlled shared agent memory

Share only approved/promoted knowledge, never raw private conversations by default. See [ADR-0209](../adr/0209-introduce-project-scoped-agent-memory.md) for the v0.2, project-isolated memory building block this extends to cross-project sharing/promotion.

### ADR-0405: Expose agent delegation traces to users

Make delegated actions understandable and auditable in the user experience.

### ADR-0406: Limit recursive agent delegation

Prevent loops and runaway cost through hop/depth and policy limits.

### ADR-0407: Add specialized task-oriented frontend views

Complement chat with structured task-specific interfaces for complex workflows.

(2026-08-18: the per-agent task-tab portion of this decision was to be delivered early by [ADR-0505](../adr/0505-open-okf-tasks-as-concurrent-per-agent-frontend-tabs.md) in the OKF stream; 2026-08-21: ADR-0505 was abandoned before implementation and superseded by [ADR-0515](../adr/0515-per-conversation-tabs-one-browser-tab-per-agent.md), which delivers per-conversation tabs with one browser tab per agent instead. The broader structured-view scope stays here.)

### ADR-0408: Automate removal of inaccessible private RAG content

Remove embeddings/content when a user loses source access.

### ADR-0409: Introduce advanced human approval workflows

Pause sensitive operations for explicit approval and resume from persisted checkpoints.
