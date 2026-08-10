# ADR-0032: Propagate trusted identity end to end

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

`components/agent-bff/internal/runtime/client.go` currently calls the Agent Runtime without forwarding the authenticated bearer token, while the Agent Runtime expects authenticated calls. `components/agent-runtime/app/clients/model_router.py` also calls the AI Gateway using `api_key="not-required"`, although the model plane is intended to enforce Keycloak-backed authentication. The current implementation therefore breaks the intended trust chain.

## Decision

Propagate trusted identity across `Frontend -> BFF -> Agent Runtime -> policy/model plane`. The BFF must forward the validated end-user bearer token to the Agent Runtime. Service-to-service calls that should not reuse the end-user token must use dedicated Keycloak service identities, with explicit On-Behalf-Of semantics where user context is required. Anonymous placeholders such as `Bearer not-required` are forbidden outside isolated local developer mocks.

## Consequences

Identity becomes explicit at every hop and auditable. Service credentials and OBO exchanges add configuration work but remove implicit trust between internal services.

## Security considerations

Tokens must be audience-scoped, short-lived and validated at the receiving service. Services must fail closed when identity validation fails.

## Operational considerations

Add integration tests that exercise a valid token, an expired token, a wrong audience, a missing token and a service identity path.

## Implementation state

**Implemented (2026-08-05).**

- `components/agent-bff/internal/runtime/client.go`'s `Chat()` takes the caller's validated bearer token as an explicit parameter, forwarded as `Authorization: Bearer <token>` to the Agent Runtime (`main.go`'s `chatHandler` passes through the same token it just verified).
- `components/agent-runtime/app/clients/model_router.py`'s `ModelRouter.chat_model_for()` no longer sends `api_key="not-required"` - it forwards the same end-user token to `components/ai-gateway`'s `/v1/chat/completions`, threaded through `invoke_with_fallback()` and `app/graph/nodes.py:reason_node` from `state["bearer_token"]`.
- Explicit scope decision: reuses the end-user token end-to-end (Frontend -> BFF -> Runtime -> AI Gateway) rather than a separate Keycloak service-identity/On-Behalf-Of exchange for the Runtime -> AI Gateway hop. `ai-gateway`'s `validate_token` only requires an authenticated caller (routing is classification-header-driven per ADR-0020/0021), so a new client-credentials flow would be unused infrastructure. The Runtime -> MCP Gateway hop already forwarded the end-user token (ADR-0013); this makes Runtime -> AI Gateway consistent with that existing pattern.
- Security-negative coverage: `evaluations/tekos/security_checks.py` verifies the BFF-to-Runtime token forward succeeds end-to-end (previously the Runtime rejected an unauthenticated BFF call with 401).

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.

## Related ADRs

- ADR-0012
- ADR-0013
- ADR-0009
