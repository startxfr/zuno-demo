# ADR-0032: Propagate trusted identity end to end

- **Status:** Implemented
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

**Implemented (2026-08-05).** `components/agent-bff/internal/runtime/client.go`'s
`Chat()` now takes the caller's validated bearer token as an explicit
parameter and forwards it as `Authorization: Bearer <token>` to the Agent
Runtime (`main.go`'s `chatHandler` passes through the same token it just
verified). `components/agent-runtime/app/clients/model_router.py`'s
`ModelRouter.chat_model_for()` no longer sends `api_key="not-required"` -
it forwards that same end-user token to `components/ai-gateway`'s
`/v1/chat/completions`, threaded through `invoke_with_fallback()` and
`app/graph/nodes.py:reason_node` from `state["bearer_token"]` (already
populated from the validated token, not request-body input).

Scope decision, made explicitly rather than silently: this reuses the
end-user token end-to-end (Frontend -> BFF -> Runtime -> AI Gateway) rather
than introducing a separate Keycloak service-identity/On-Behalf-Of
exchange for the Runtime -> AI Gateway hop. `ai-gateway`'s own
`validate_token` only requires an authenticated caller and makes no
identity/group-based authorization decision (routing is
classification-header-driven per ADR-0020/0021) - standing up a new
client-credentials flow for that hop would be new infrastructure nothing
downstream currently consumes. The Runtime -> MCP Gateway hop already
forwarded the end-user token before this ADR (ADR-0013); this ADR makes
the Runtime -> AI Gateway hop consistent with that existing pattern rather
than inventing a second identity mechanism.

Security-negative coverage: `evaluations/tekos/security_checks.py`
verifies the BFF-to-Runtime token forward succeeds end-to-end (previously
the Runtime would reject an unauthenticated call from the BFF with 401).

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
