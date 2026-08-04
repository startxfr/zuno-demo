# ADR-0033: Derive user identity only from validated tokens

- **Status:** Implemented
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

**Implemented (2026-08-05).** `components/agent-runtime/app/main.py`'s
`_initial_state()` now sets graph state's `user_sub` from
`identity.sub` (the validated token's own claim), never from
`payload.user_sub` (the request body). A mismatch between the two is
logged (informational - useful for catching a BFF bug) but no longer
influences behavior in any way; `app/schemas.py`'s `ChatRequest.user_sub`
field comment and `README.md`'s HTTP API contract both now say explicitly
that the field is correlation/display metadata only. This closes the
concrete gap the ADR's Context section named: the Runtime previously used
`payload.user_sub` for graph state (line 60's old code) despite only
*logging* a warning on mismatch rather than ignoring the field.

Security-negative coverage: `evaluations/tekos/security_checks.py`'s
`runtime_ignores_mismatched_user_sub` submits a valid token for one
persona with a forged, nonexistent `user_sub` in the body and verifies
the call still succeeds normally - proving impersonation via this field
is impossible because the field is never trusted, per this ADR's
Operational considerations.

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
