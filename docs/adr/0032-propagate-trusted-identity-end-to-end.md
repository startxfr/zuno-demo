# ADR-0032: Propagate trusted identity end to end

- **Status:** To be implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

`components/agent-bff/internal/runtime/client.go` currently calls the Agent Runtime without forwarding the authenticated bearer token, while the Agent Runtime expects authenticated calls. `components/agent-runtime/app/clients/model_router.py` also calls the AI Gateway using `api_key="not-required"`, although the model plane is intended to enforce Keycloak-backed authentication. The current implementation therefore breaks the intended trust chain.

## Decision

Propagate trusted identity across `Frontend -> BFF -> Agent Runtime -> policy/model plane`. The BFF must forward the validated end-user bearer token to the Agent Runtime. Service-to-service calls that should not reuse the end-user token must use dedicated Keycloak service identities, with explicit On-Behalf-Of semantics where user context is required. Anonymous placeholders such as `Bearer not-required` are forbidden outside isolated local developer mocks.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

Identity becomes explicit at every hop and auditable. Service credentials and OBO exchanges add configuration work but remove implicit trust between internal services.

## Security considerations

Tokens must be audience-scoped, short-lived and validated at the receiving service. Services must fail closed when identity validation fails.

## Operational considerations

Add integration tests that exercise a valid token, an expired token, a wrong audience, a missing token and a service identity path.

## Implementation state

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0012
- ADR-0013
- ADR-0009

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
