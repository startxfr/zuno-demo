# ADR-0042: Use opaque browser sessions with server-side token storage

- **Status:** Implemented — see `components/agent-frontend/internal/session/{session,store}.go`, `gitops/charts/redis/`, `ansible/roles/redis/`.
- **Target:** v1
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The frontend currently carries access/ID tokens in a signed browser cookie. Although HttpOnly/Secure protection helps, signed cookies are not encrypted, token payloads are repeated on requests and large JWT sets approach cookie size limits. Longer-lived workflows also benefit from server-side session control.

## Decision

Store only an opaque session identifier in the browser. Keep access token, refresh token, groups, expiry and delegated provider tokens in a server-side session store such as Redis, with encryption at rest where applicable and explicit revocation/TTL. The frontend/BFF resolves the opaque session before downstream calls.

## Consequences

Session revocation, token refresh and long-running workflows become easier to control. Redis or an equivalent HA session dependency becomes part of the industrialized platform.

## Security considerations

Session records must be user-isolated, short-lived by default, revocable and excluded from logs. Refresh tokens receive stronger protection than access tokens.

## Operational considerations

Implement before production hardening; v0 may keep the current model only if token exposure remains bounded and documented.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Implementation state, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0013](0013-propagate-end-user-identity-through-agent-calls.md)
- ADR-0101
- ADR-0103
