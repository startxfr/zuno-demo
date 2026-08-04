# ADR-0040: Separate agent entitlement from business role authorization

- **Status:** To be implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The current Keycloak realm primarily uses business groups such as `sales`, `consultant`, `adv`, `finance` and `board` to both describe personas and grant frontend access. The project requirements also define explicit `agent_<name>` entitlement groups and business roles such as `sales_admin`. Mixing these concerns makes authorization difficult to reason about as the catalog grows.

## Decision

Use two orthogonal Keycloak group/role dimensions. Agent entitlement groups (`agent_comage`, `agent_tekos`, `agent_arkos`, `agent_advantage`, `agent_finage`) control whether a user may access an agent. Business groups/roles (`sales`, `sales_admin`, `consultant`, `adv`, `finance`, `board`, etc.) control data and tool permissions inside authorized agents.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

A user can be entitled to several agents while retaining one or more business roles. Policies become more explicit and scalable.

## Security considerations

Frontend visibility must not be treated as authorization. BFF, Runtime and MCP Gateway must enforce entitlement/role claims server side.

## Operational considerations

Migrate Keycloak realm fixtures and policy tests. Add tests for users with entitlement but insufficient business role and vice versa.

## Implementation state

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0012
- ADR-0011

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
