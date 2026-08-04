# ADR-0054: Define the BFF contract OpenAPI-first

- **Status:** To be implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The project requires versioned BFF APIs with Swagger/OpenAPI, but the reviewed Go BFF currently relies on hand-written request/response structs and comments describing the Runtime contract. This has already allowed identity and streaming expectations to diverge between components.

## Decision

Create a versioned OpenAPI specification for the agent BFF API and use it as the contract source for Go handlers/clients and frontend integration. Include chat/session endpoints, task discovery, SSE event schemas, citations, approvals/errors and authentication requirements. Generate code where practical and validate backward compatibility in CI.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

API drift is reduced and every agent BFF exposes consistent Swagger documentation. Contract changes become explicit review events.

## Security considerations

The specification must clearly mark authenticated operations, never expose internal tokens in schemas, and document authorization failures without leaking policy internals.

## Operational considerations

Add OpenAPI linting and contract tests between frontend, BFF and Runtime adapters.

## Implementation state

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0008
- ADR-0032
- ADR-0033
- ADR-0045

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
