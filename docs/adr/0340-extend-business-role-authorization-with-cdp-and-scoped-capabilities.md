# ADR-0340: Extend business-role authorization with CDP and scoped capabilities

- **Status:** Partially implemented (policy and realm merged; realm re-apply pending)
- **Target:** v0.3
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0040 separates agent entitlement from business-role authorization using Keycloak groups such as `consultant`, `sales`, `adv`, `finance` and `board`. The target organization now explicitly includes project managers (`cdp`) and requires more precise resource scopes, especially for Workday where a technical user may read/write only their own profile while a project manager may read profiles for managed staff without receiving write access.

Creating a new AI-profile database would duplicate Keycloak and make policy drift likely.

## Decision

Keep Keycloak business roles as the identity source of truth and extend the business-role vocabulary with `cdp`.

Use the following conceptual role mapping for the target platform:

- technical population -> existing `consultant` role;
- project manager -> new `cdp` role;
- sales -> `sales`;
- ADV -> `adv`;
- direction -> existing `board`;
- finance -> `finance`.

`architecture`, `build` and `run` are **technical skill/data scopes**, not business roles. In particular, the temporary ADR-0330 demo use of `/board` as an architect container must be migrated so `board` can consistently mean Direction.

Represent resource scope in logical capabilities/policy rather than broad role names. In particular, Workday exposes separate capabilities such as:

- `workday.profile.self.read`
- `workday.profile.self.update`
- `workday.profile.any.read`

Technical users receive self read/write; CDP receives read access through `self.read`/`any.read` according to organizational scope. CDP write access is not implied. `any.update` is not implied and must be a separately approved capability if ever introduced.

Apply the same read/write separation to Jira, Confluence, Salesforce and Google Workspace. A role matrix is documentation/derived output, **not an independent authorization source**: effective authorization remains the intersection of Keycloak business role, agent/task OKF declarations, classification/data policy and platform policy.

Initial intended access pattern from the current requirements is:

| Capability family | consultant/tech | cdp | sales | adv | board/direction | finance |
|---|---|---|---|---|---|---|
| `knowledge.tech` | R | policy-defined | - | - | policy-defined | - |
| `knowledge.sales` | - | policy-defined | R | policy-defined | policy-defined | policy-defined |
| `knowledge.sxa-legacy` | - | - | R | - | R | - |
| `knowledge.adv` | - | policy-defined | - | R | policy-defined | policy-defined |
| Confluence/Jira | RW | RW | - | - | - | - |
| Drive | RW | RW | RW | RW | RW | RW |
| Gmail | RW | RW | RW | RW | RW | RW |
| Calendar/Meet | RW | RW | RW | RW | RW | RW |
| Salesforce | - | policy-defined | RW | policy-defined | policy-defined | policy-defined |
| Workday self | RW | R | - | - | - | - |
| Workday any | - | R | - | - | - | - |

The table is an initial policy intent and must be encoded in the authoritative policy files before it becomes effective.

## Consequences

Project-manager requirements fit the existing identity architecture. Fine-grained scopes avoid giving broad organization-wide write rights merely because a user needs one read use case.

## Security considerations

Group hierarchy must not accidentally make `cdp` or `board` a universal bypass. Resource ownership/organizational-scope checks for `*.self.*` / `*.any.*` are enforced server-side from validated identity claims/provider data, not prompt text.

## Operational considerations

Policy tests cover positive and negative combinations for each new role/scope. The documentation matrix should be generated or checked against authoritative policy to reduce drift.

## Acceptance criteria

- Keycloak contains a `cdp` business role without changing agent-entitlement semantics.
- A technical user can update only their own Workday profile when granted `self.update`.
- A CDP can read authorized staff profiles with `any.read` but cannot update them without a separate write capability.
- A role cannot use a capability absent from the active agent/task OKF declaration.
- No independent AI-profile store is required.

## Evolution (2026-08-14)

ADR-0349 advances one element of this decision ahead of its v0.3 target: the `confluence-archi-*` subgroups and their membership move from `board` to `consultant`, so `board` consistently means Direction. The `cdp` role and the capability-scope model remain at v0.3.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md)
- [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md)
- [ADR-0203](0203-enforce-knowledge-authorization-as-policy-intersection.md)
- [ADR-0116](0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md)
- [ADR-0208](0208-standardize-enterprise-tool-authentication-and-delegation.md)
