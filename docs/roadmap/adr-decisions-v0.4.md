# v0.4 roadmap decisions (ADR-0401 – ADR-0409)

- **Status:** Proposed
- **Target:** v0.4
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team

Consolidated from 9 individual ADR files. Each entry below is its own immutable decision record, citable as `ADR-0NNN`; only the Decision line is unique per entry - [Standard clauses](README.md#standard-clauses) (Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution, Related ADRs) apply to every entry unless overridden here.

These nine decisions were originally drafted as ADR-0201–0209 under the v0.2 roadmap. They moved here because agent-to-agent (A2A) delegation and cross-agent shared memory are only meaningful once multiple agents actually exist to delegate to and share with - that is a v0.3 outcome (see [ADR-0326](../adr/0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md)). v0.2 is scoped to maturing the single-agent (Tekos) MCP/RAG/model-routing pattern; v0.4 is where that pattern is extended across agents through delegation.

### ADR-0401: Introduce agent-to-agent communication

Promoted to a full decision record (2026-10-24, retargeted to v0.11, UnifAI stream): see [ADR-0401](../adr/0401-introduce-agent-delegation-limited-to-targets-an-agent-declares.md).

### ADR-0402: Adopt A2A as the inter-agent protocol

Promoted to a full decision record (2026-10-24, retargeted to v0.11, UnifAI stream): see [ADR-0402](../adr/0402-adopt-a2a-as-the-inter-agent-protocol.md).

### ADR-0403: Propagate user identity across agent-to-agent calls

Promoted to a full decision record (2026-10-24, retargeted to v0.11, UnifAI stream): see [ADR-0403](../adr/0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md).

### ADR-0404: Introduce controlled shared agent memory

Share only approved/promoted knowledge, never raw private conversations by default. See [ADR-0209](../adr/0209-introduce-project-scoped-agent-memory.md) for the v0.2, project-isolated memory building block this extends to cross-project sharing/promotion.

### ADR-0405: Expose agent delegation traces to users

Make delegated actions understandable and auditable in the user experience.

### ADR-0406: Limit recursive agent delegation

Promoted to a full decision record (2026-10-24, retargeted to v0.11, UnifAI stream): see [ADR-0406](../adr/0406-limit-agent-delegation-by-depth-cycle-and-budget.md).

### ADR-0407: Add specialized task-oriented frontend views

Complement chat with structured task-specific interfaces for complex workflows.

(2026-08-18: the per-agent task-tab portion of this decision was to be delivered early by [ADR-0505](../adr/0505-open-okf-tasks-as-concurrent-per-agent-frontend-tabs.md) in the OKF stream; 2026-08-21: ADR-0505 was abandoned before implementation and superseded by [ADR-0515](../adr/0515-per-conversation-tabs-one-browser-tab-per-agent.md), which delivers per-conversation tabs with one browser tab per agent instead. The broader structured-view scope stays here.)

### ADR-0408: Automate removal of inaccessible private RAG content

Remove embeddings/content when a user loses source access.

### ADR-0409: Introduce advanced human approval workflows

Promoted to a full decision record (2026-10-24, retargeted to v0.11, UnifAI stream): see [ADR-0409](../adr/0409-introduce-human-approval-for-delegated-operations-resumable-from-persisted-checkpoints.md).

## Reassessment (2026-10-24) - against the UnifAI platform

These stubs predate [ADR-0561](../adr/0561-adopt-unifai-as-the-agent-platform.md).
No status changes here; each row records what the UnifAI fork already provides
and what remains, so that a later decision can promote, amend or supersede it.

Rows 0401, 0402, 0403, 0406 and 0409 were promoted on the same day (see their records); the table keeps what each found.

| ADR | Already provided | Open |
|---|---|---|
| 0401 | `A2AAgentNode` and `A2AProvider` in `startx-unifai` | zuno authorisation policy for delegation |
| 0402 | the nodes use the `a2a-sdk` | none: adoption is a fact, a decision can say so |
| 0403 | none found in the A2A node (WP-146 forwards the user JWT to MCP only) | **the real gap**: carry the initiating user's identity across A2A calls |
| 0404 | project memory ([WP-148](work-packages/wp-148-unifai-parity-memory-routing-quota-ux.md)) | sharing promoted knowledge across agents |
| 0405 | OTel spans ([WP-147](work-packages/wp-147-unifai-opentelemetry-instrumentation.md)) | user-facing display of delegation traces |
| 0406 | LangGraph recursion limit, thread-depth cycle guard (50) | hop and budget limits per delegation |
| 0407 | per-agent entry and sheet ([WP-167](work-packages/wp-167-per-agent-entry-and-sheet.md), ADR-0582) | task-oriented views beyond chat |
| 0408 | group ACLs, incremental sync and stale-point deletion ([WP-149](work-packages/wp-149-unifai-rag-qdrant-hybrid-sources-backup.md)) | verify revocation removes private content |
| 0409 | `ChannelApprovalGate` (HITL) in the fork | mapping to zuno policy and persisted checkpoints |

