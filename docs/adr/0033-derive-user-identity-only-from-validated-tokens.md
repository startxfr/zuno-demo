# ADR-0033: Derive user identity only from validated tokens

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The BFF/Runtime chat contract currently carries a user-controlled `user_sub` field in the JSON body. A caller can therefore submit an identity value that differs from the authenticated JWT unless every downstream component explicitly rejects the mismatch.

## Decision

Remove caller-supplied identity as an authorization source. The Agent Runtime must derive user subject, groups and relevant claims exclusively from the validated access token. If a request payload contains a user identifier for correlation or display, it is informational only and must match the token or be ignored.

## Consequences

Authorization decisions no longer depend on mutable request fields. API contracts become simpler and impersonation risk is reduced.

## Security considerations

Never authorize tools, data, tasks or agent access using `user_sub` from request JSON. Security-sensitive identity comes from validated token claims only.

## Operational considerations

Update BFF OpenAPI contracts, runtime models and tests. Add a negative test that submits a different `user_sub` and verifies that impersonation is impossible.

## Implementation state

**Implemented (2026-08-05).**

- `components/agent-runtime/app/main.py`'s `_initial_state()` now sets graph state's `user_sub` from `identity.sub` (the validated token's own claim), never from `payload.user_sub` (the request body). A mismatch is logged (informational only) but no longer influences behavior; `app/schemas.py`'s `ChatRequest.user_sub` field comment and `README.md`'s HTTP API contract both now say explicitly that the field is correlation/display metadata only.
- Closes the concrete gap the ADR's Context named: the Runtime previously used `payload.user_sub` for graph state despite only *logging* a warning on mismatch rather than ignoring the field.
- Security-negative coverage: `evaluations/tekos/security_checks.py`'s `runtime_ignores_mismatched_user_sub` submits a valid token for one persona with a forged, nonexistent `user_sub` in the body and verifies the call still succeeds normally, proving impersonation via this field is impossible.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.

## Related ADRs

- ADR-0013
- ADR-0032
