# ADR-0033: Derive user identity only from validated tokens

- **Status:** To be implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The BFF/Runtime chat contract currently carries a user-controlled `user_sub` field in the JSON body. A caller can therefore submit an identity value that differs from the authenticated JWT unless every downstream component explicitly rejects the mismatch.

## Decision

Remove caller-supplied identity as an authorization source. The Agent Runtime must derive user subject, groups and relevant claims exclusively from the validated access token. If a request payload contains a user identifier for correlation or display, it is informational only and must match the token or be ignored.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

Authorization decisions no longer depend on mutable request fields. API contracts become simpler and impersonation risk is reduced.

## Security considerations

Never authorize tools, data, tasks or agent access using `user_sub` from request JSON. Security-sensitive identity comes from validated token claims only.

## Operational considerations

Update BFF OpenAPI contracts, runtime models and tests. Add a negative test that submits a different `user_sub` and verifies that impersonation is impossible.

## Implementation state

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0013
- ADR-0032

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
