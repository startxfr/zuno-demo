# ADR-0583: Require group visibility and object-level authorisation before per-agent entries

- **Status:** Proposed
- **Target:** v0.12
- **Date:** 2026-10-22
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0564](0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md) (clause 5, entitlement), [ADR-0562](0562-authenticate-unifai-against-the-zuno-keycloak-realm.md), [ADR-0563](0563-forward-caller-identity-and-zuno-context-headers-from-unifai.md)
- **Related:** [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md), [ADR-0573](0573-pilot-unifai-on-demo333-with-tekos-before-cutting-demo222-over.md), [ADR-0575](0575-upstream-generic-unifai-changes-and-isolate-zuno-specific-code.md), [ADR-0582](0582-serve-a-per-agent-entry-and-descriptive-sheet-from-the-admitted-bundle.md)

## Context

ADR-0564 refuses a bundle with `EntitlementUnsupported` when UnifAI cannot
restrict an agent to groups, unless `spec.entitlement: GatewayOnly` is set.
`GatewayOnly` leaves the agent visible and runnable by every authenticated
UnifAI user, with only the ai-gateway and the mcp-gateway filtering by the
forwarded token (ADR-0563). ADR-0573 makes "a user without `agent_tekos`
cannot use Tekos" an exit criterion of the pilot, and the parity table marks
group-gated visibility unverified.

Objects of the unifai-operator bundles all belong to one privileged owner in
one workspace. Whether every read of a blueprint, an agent or a session
checks the caller against the object, rather than trusting that identifiers
are hard to guess, has not been established for the fork.

A per-agent entry (ADR-0582) makes both gaps visible and easy to use, so they
are prerequisites, not follow-ups.

### Evidence from the pilot (demo333, 2026-10-22)

Measured on the live pilot stack: UnifAI visibility is owner or team
workspace. An object owned by one persona is invisible to the others (the
list is empty); selecting a team workspace (`teamId` on each request) shows it;
a non-member gets `403 TEAM_ACCESS_DENIED`. Teams hold user members or LDAP
group members only, because the identity directory provider supports `ldap`
only (`shared-resources/identity/directory/factory.py`). No source exists for
OIDC groups, so a team cannot be "all members of `agent_<name>`". The identity
service already receives the user's access token when it caches groups, so a
claims-based provider is a small generic change. For the pilot a team was
created by hand and the bundle takes a `teamId`; that does not scale.

## Decision

**No per-agent entry is exposed until UnifAI itself restricts visibility by
group and checks authorisation on every object read.**

1. **Group visibility in UnifAI.** The operator emits, and UnifAI honours, a
   group restriction per agent derived from `zuno.access.groups`, using the
   `oidc-claims` mechanism of ADR-0562 and WP-146: a generic `oidc-claims`
   directory provider in the identity service reads groups from the verified
   access token claims, a team references a group, and the operator emits the
   `teamId` of the team bound to the agent's group. `GatewayOnly` stays a
   documented escape hatch for stacks without per-agent entries and is
   refused when an entry or sheet is enabled.
2. **Object-level authorisation audit.** Before ADR-0582 is implemented, the
   fork's read and list endpoints for blueprints, agents, sessions and
   executions are audited: each must check the caller against the object
   (owner, shared-with, or group). Findings are fixed in the generic code and
   offered upstream (ADR-0575). Details of an unfixed finding are kept out of
   public commits and records until the fix has landed.
3. **Uniform denial.** Unauthorised and non-existent objects return the same
   response and timing class, so an identifier or an agent name cannot be
   probed.
4. **Session isolation.** Resuming or reading a session of another user is
   refused; the pilot verifies it (ADR-0561 marks it unverified).
5. **Tests as the gate.** The criteria of clauses 1, 3 and 4 become automated
   tests in the fork and in the pilot evaluation (WP-154) with two users in
   different groups.

## Consequences

Per-agent entries wait on fork work that is useful on its own: it also
protects the existing chat and blueprint surfaces. If the audit finds gaps,
the first release of ADR-0582 slips behind their fix.

## Security considerations

This ADR exists to close an authorisation gap, not to add a feature. The
gateways remain the policy enforcement points for models and tools, so a
frontend bug cannot grant model or tool access, but it can still disclose
agent definitions, prompts and conversations. Treat the audit result as
sensitive until fixed.

## Operational considerations

Work happens in the fork, upstream-first. The operator needs a release for the
group restriction. The pilot on demo333 is the first place to verify it; no
change to demo222 until the cutover (ADR-0573).
