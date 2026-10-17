# ADR-0562: Authenticate UnifAI against the zuno Keycloak realm

- **Status:** Accepted
- **Target:** v0.11
- **Date:** 2026-10-17
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0530](0530-reconcile-keycloak-clients-instead-of-relying-on-a-create-only-realm-import.md) (reconcile Keycloak clients instead of relying on a create-only realm import)
- **Related:** [ADR-0012](0012-use-keycloak-as-the-central-identity-provider.md), [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md), [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md), [ADR-0563](0563-forward-caller-identity-and-zuno-context-headers-from-unifai.md), [ADR-0574](0574-deploy-unifai-through-argocd-from-a-pinned-olm-catalog.md), [ADR-0575](0575-upstream-generic-unifai-changes-and-isolate-zuno-specific-code.md)

## Context

ADR-0561 adopts UnifAI as the agent platform. UnifAI authenticates users
through its own `identity` service (`shared-resources/identity` in the fork):
an OIDC authorization-code flow against a Keycloak realm, after which the
session, including the user's tokens, is kept server-side in Redis and the UI
carries only a session cookie (`shared-resources/identity/README.md`). Every
other UnifAI service either validates that session against Redis or trusts an
`X-Authenticated-User` header stamped by an internal caller
(`rag/infrastructure/http/auth.py`); the fork's operator restricts ingress
with the `unifai-stack` NetworkPolicy precisely because of that trust
(`fork/unifai-operator/README.md`).

The operator offers two identity modes on `UnifaiStack.spec.identity`
(`fork/unifai-operator/api/v1alpha1/unifaistack_types.go`): `keycloak`, which
installs RHBK, a database and a `KeycloakRealmImport` for a dedicated realm
`unifai` in the stack namespace; and `external`, which points at an existing
realm through `url`, `realm`, `clientId` and a `clientSecret` Secret selector.
Both modes are live on `demo333`: `unifai-olm` runs a managed Keycloak, and
`unifai-devel` uses the zuno RHBK instance in `zuno-auth` but a **separate
realm `unifai`**, created by hand with a `KeycloakRealmImport` and a single
`admin` user (`MEMORY.md` of the fork, section "Clusters").

Neither arrangement can serve zuno. Every zuno persona, business-role group
(`board`, `consultant`, `sales`, `adv`, `finance`, ...) and agent-entitlement
group (`agent_tekos`, `agent_comage`, ...) lives in realm `zuno`
(`gitops/charts/keycloak/files/realm-zuno.json`). The ai-gateway and the
mcp-gateway validate JWTs against that realm's issuer
(`components/ai-gateway/app/auth.py`, `components/mcp-gateway/app/auth.py`),
and the mcp-gateway authorizes on the token's `groups` claim. A token minted
by realm `unifai` or by a namespace-local Keycloak is rejected by both, which
would make ADR-0563's identity forwarding impossible.

The client cannot simply be added to `realm-zuno.json` and assumed live. The
realm import runs with `--override=false` and is never re-run once the realm
exists; ADR-0530 added a Sync-hook Job (`job-client-reconcile.yaml`) that
reconciles **clients and their service-account role mappings only**, while
groups, users, realm roles and client scopes remain create-only.

## Decision

**UnifAI authenticates against realm `zuno`, never against a realm of its
own.** Every `UnifaiStack` rendered by zuno uses `spec.identity.external`
with `realm: zuno` and `clientId: unifai`. The `identity.keycloak` mode is not
used on zuno clusters, and the hand-made realm `unifai` on `demo333` is
retired once `unifai-devel` has been moved to realm `zuno` (WP-151).

**The `unifai` client is declared in `realm-zuno.json` and provisioned by the
ADR-0530 reconcile Job**, so it reaches a live realm on every sync and on a
from-scratch install alike. Its shape follows the existing confidential
`*-frontend` clients:

- confidential (`publicClient: false`), standard flow on, implicit flow off,
  direct access grants **off** (UnifAI never needs a password grant; the
  `*-frontend` clients keep theirs for test personas, `unifai` does not);
- `redirectUris`, `webOrigins` and `post.logout.redirect.uris` limited to the
  UI and identity hosts the operator exposes
  (`unifai-ui-<namespace>.apps.<domain>` and
  `unifai-identity-<namespace>.apps.<domain>`, or the hosts set in
  `spec.exposure`), written with the same `apps.mycluster.example.com`
  placeholder the other clients use;
- protocol mappers copied from the `*-frontend` clients: the `groups`
  group-membership mapper (`full.path: true`, in the access token), an
  `audience-self` mapper, and whatever audience the downstream gateways
  require once ADR-0563 forwards the token. Today neither gateway enforces
  `aud` (`JWT_AUDIENCE` unset), so no new audience mapper is added before one
  of them does.

**The client secret follows ADR-0530 clause 6.** It is Vault-seeded at
`keycloak/unifai-client` by `ansible/roles/vault`, referenced in the realm
file as a `${vault.*}` placeholder resolved by Keycloak's file vault, and
delivered to the UnifAI namespace by an `ExternalSecret` that materializes
the Secret named in `identity.external.clientSecret`. No client secret is
written into a CR, a values file or the fork.

**Users, groups and personas are not duplicated.** No UnifAI-specific users
are created; zuno personas log in with their existing realm accounts. Realm
groups are the single source of business roles and agent entitlement
(ADR-0040). UnifAI administrators are named through
`spec.identity.adminUsers`, which the operator renders into UnifAI's
`admin_allowed_users` list; the list holds realm usernames and is kept to the
platform operators.

**Group membership must reach UnifAI from the token, not from LDAP.**
UnifAI resolves a user's groups through a directory provider, and the only
provider implemented is `ldap` (`shared-resources/identity/directory/factory.py`).
Zuno has no LDAP; its groups are carried by the `groups` claim. The fork
therefore gains a generic `oidc-claims` directory provider that reads group
membership from the validated token (WP-146, upstreamable under ADR-0575).
Until it exists, UnifAI's own sharing model cannot honour ADR-0040
entitlement, and the gateways' checks on the forwarded token (ADR-0563) are
the only enforcement of it; that is acceptable for the `demo333` pilot and is
a cutover gate for `demo222`.

## Consequences

One identity for the whole platform: a persona who can use Tekos today can
sign into UnifAI with the same credentials, and the token UnifAI holds is one
the ai-gateway and mcp-gateway already accept. This is the precondition for
ADR-0563.

The operator's managed-Keycloak mode and the fork's dedicated realm become
irrelevant to zuno. They remain useful upstream and in the fork's own test
stack (`unifai-olm`), so nothing is removed from the operator.

Adding the client is a realm-file change plus a Vault seed, both of which
already have a working path; the cost is one more client the reconcile Job
manages. Group or mapper changes outside the client itself (a new realm
group, a client scope) stay create-only and need the Admin REST API on an
existing realm, exactly as ADR-0530 clause 4 states.

The `oidc-claims` directory provider is new fork code with no upstream
equivalent; until upstream accepts it, it is fork delta to carry on every
rebase.

## Security considerations

A single realm means a compromise of the `unifai` client secret yields a
client that can run the authorization-code flow for any zuno user. The
secret lives only in Vault, the Keycloak vault mount and one Secret in the
UnifAI namespace; it is never logged or rendered into a CR status.

UnifAI stores refresh tokens server-side in Redis (`identity` README, logout
section). Redis in the UnifAI namespace therefore holds zuno realm refresh
tokens: its Route must stay disabled (the operator exposes only the UI and
identity Routes unless `spec.exposure.exposeInternal` is set) and the
`unifai-stack` NetworkPolicy must stay enabled. The fork's `MEMORY.md` records
that the upstream charts create public, unauthenticated Routes for Qdrant,
Redis Insight and Temporal; those Routes must not exist on a zuno cluster.

The `X-Authenticated-User` trust inside the UnifAI namespace is not changed
by this decision. It is only safe while every path into the namespace passes
the identity service or the NetworkPolicy; any new ingress (a Route, a mesh
gateway, a cross-namespace caller) reopens it.

Direct access grants stay off on `unifai`, so a leaked client secret cannot be
combined with a password to mint tokens without the browser flow.

## Operational considerations

Never assume a realm-file edit landed. After the first sync, verify the
client in the live realm through the Admin REST API (token from the
`keycloak-admin` Secret against `/realms/master`), and check its redirect URIs
and mappers, not only its existence. `kcadm.sh update -f` must be used with
`-m`, and `CLIENT.DESCRIPTION` is `varchar(255)`.

The UnifAI identity pod must trust the certificate of the Keycloak Route.
On clusters using the publicly trusted wildcard certificate (ADR-0211) this
is automatic; on any cluster where Keycloak's Route certificate is not
publicly trusted, the CA must be mounted into the identity pod before login
works.

Every command against a cluster passes `--context` explicitly. `demo333` is
powered off at the time of writing; WP-151's live steps start by asking the
user to power it on.
