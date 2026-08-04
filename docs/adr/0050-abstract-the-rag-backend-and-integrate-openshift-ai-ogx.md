# ADR-0050: Abstract the RAG backend and integrate OpenShift AI OGX

- **Status:** To be implemented
- **Target:** v1
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The custom `rag-service` provides PostgreSQL/pgvector hybrid retrieval and is useful as a controllable MVP implementation. OpenShift AI 3.5 also introduces OGX/RAG capabilities that align with the project objective to demonstrate OpenShift AI components, but those capabilities may have EA/TP lifecycle constraints.

## Decision

Define a stable internal RAG API/provider interface used by Agent Runtime. Keep PostgreSQL/pgvector as the v0 fallback/reference provider and add an OGX-backed provider for OpenShift AI 3.5. Agent definitions select logical collections, not backend-specific APIs.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

The platform can demonstrate OGX without making all agent behavior depend on one preview implementation. RAG metadata contracts must remain portable across providers.

## Security considerations

Both providers must enforce classification and ACL filters consistently. Switching provider must not widen accessible data.

## Operational considerations

Create parity tests covering retrieval quality, filtering, citations and classification propagation across pgvector and OGX providers.

## Implementation state

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0015
- ADR-0018
- ADR-0046

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
