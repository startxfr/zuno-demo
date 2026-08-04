# ADR-0042: Use opaque browser sessions with server-side token storage

- **Status:** To be implemented
- **Target:** v1
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The frontend currently carries access/ID tokens in a signed browser cookie. Although HttpOnly/Secure protection helps, signed cookies are not encrypted, token payloads are repeated on requests and large JWT sets approach cookie size limits. Longer-lived workflows also benefit from server-side session control.

## Decision

Store only an opaque session identifier in the browser. Keep access token, refresh token, groups, expiry and delegated provider tokens in a server-side session store such as Redis, with encryption at rest where applicable and explicit revocation/TTL. The frontend/BFF resolves the opaque session before downstream calls.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

Session revocation, token refresh and long-running workflows become easier to control. Redis or an equivalent HA session dependency becomes part of the industrialized platform.

## Security considerations

Session records must be user-isolated, short-lived by default, revocable and excluded from logs. Refresh tokens receive stronger protection than access tokens.

## Operational considerations

Implement before production hardening; v0 may keep the current model only if token exposure remains bounded and documented.

## Implementation state

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0013
- ADR-0101
- ADR-0103

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
