# ADR-0034: Compute effective classification from the complete context

- **Status:** To be implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

Tekos currently uses a static `TEKOS_DATA_CLASSIFICATION = "C1"` in `components/agent-runtime/app/graph/nodes.py`. The same workflow can retrieve public C1 documentation and C2 Confluence material. A static request classification can therefore under-classify the final model context.

## Decision

Compute an effective classification for every reasoning step from the highest sensitivity of all contributing inputs: user request, retrieved documents, tool results, conversation memory and generated intermediate artifacts. The effective classification must be propagated to model routing, logging/redaction policy, cache policy and downstream tools.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

Model eligibility and data handling follow the actual context rather than the agent default. This requires classification metadata on RAG documents and MCP results.

## Security considerations

Classification must only stay the same or become more restrictive as context is accumulated. A downstream step must never downgrade classification automatically.

## Operational considerations

Implement classification aggregation in Agent Runtime state and add tests for C1-only, C1+C2 and C3 contexts.

## Implementation state

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0021
- ADR-0035
- ADR-0046

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
