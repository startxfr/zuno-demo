# ADR-0040: Separate agent entitlement from business role authorization

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The current Keycloak realm primarily uses business groups such as `sales`, `consultant`, `adv`, `finance` and `board` to both describe personas and grant frontend access. The project requirements also define explicit `agent_<name>` entitlement groups and business roles such as `sales_admin`. Mixing these concerns makes authorization difficult to reason about as the catalog grows.

## Decision

Use two orthogonal Keycloak group/role dimensions. Agent entitlement groups (`agent_comage`, `agent_tekos`, `agent_arkos`, `agent_advantage`, `agent_finage`) control whether a user may access an agent. Business groups/roles (`sales`, `sales_admin`, `consultant`, `adv`, `finance`, `board`, etc.) control data and tool permissions inside authorized agents.

## Consequences

A user can be entitled to several agents while retaining one or more business roles. Policies become more explicit and scalable.

## Security considerations

Frontend visibility must not be treated as authorization. BFF, Runtime and MCP Gateway must enforce entitlement/role claims server side.

## Operational considerations

Migrate Keycloak realm fixtures and policy tests. Add tests for users with entitlement but insufficient business role and vice versa.

## Implementation state

**Implemented (2026-08-05).**

- `gitops/charts/keycloak/files/realm-zuno.json` now defines two orthogonal group dimensions: five `agent_<name>` entitlement groups (`agent_comage`, `agent_tekos`, `agent_advantage`, `agent_finage`, `agent_arkos`, each holding the `clientRoles` mapping to its frontend's `access` role, the only groups that carry one), and five business-role groups (`sales`, `consultant`, `adv`, `finance`, `board`) with no `clientRoles` of their own, plus a `sales_admin` subgroup of `sales` (reserved - Comage has no runtime yet in v0). `agents/*/agent.okf.yaml`'s `spec.access.groups` was updated from the business group to the matching `agent_<name>` group for all five agents.
- Frontend tile visibility (`components/agent-frontend/internal/portal`) was never itself authorization and remains only a UX signal. Server-side enforcement is now in two places: `components/agent-bff/main.go`'s `chatHandler` rejects a call with `403` unless the validated token's `groups` claim contains `agent_<AGENT_NAME>` (new check), and `components/mcp-gateway/app/policy.py`'s existing `user_group_rights` factor continues to enforce the business-role groups against `policies/tools/tool-policy.yaml`'s `allowed_groups`, unchanged.
- New tests in `evaluations/tekos/security_checks.py`: `entitlement_without_business_role_denied_confluence` (persona `tekos-entitlement-only-user-01`: `agent_tekos` only, no business role - MCP Gateway must still deny `search_confluence` with 403) and `business_role_without_entitlement_denied_by_bff` (persona `consultant-role-only-user-01`: `consultant` only, no `agent_tekos` - the BFF must deny the call with 403 before it reaches the Agent Runtime).

## Evolution (2026-08-13)

ADR-0340 retains this two-dimensional identity model and adds `cdp` as a business role for project-management capabilities. Existing `consultant` maps to the technical population and `board` remains the direction-level role. No separate AI-profile identity store is introduced; role-to-capability matrices are documentation/views derived from Keycloak groups, OKF declarations and platform policies.

## Evolution (2026-08-14)

ADR-0349 keeps both dimensions and their semantics but redefines the membership matrix (renamed personas, new `sale-*`/`recrut-*` users, `agent_soursage`/`agent_cognos` entitlement groups, a `recrut` business role) and relocates the `confluence-archi-*` ACL subgroups from `board` to `consultant`. The two negative-test fixture personas defined by this ADR are preserved unchanged.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0012](0012-use-keycloak-as-the-central-identity-provider.md)
- [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md)
