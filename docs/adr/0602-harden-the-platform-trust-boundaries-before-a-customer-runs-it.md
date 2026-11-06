# ADR-0602: Harden the platform's trust boundaries before a customer runs it

- **Status:** Proposed
- **Target:** v0.15
- **Date:** 2026-11-06
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md), [ADR-0024](0024-use-vault-for-application-secrets.md), [ADR-0033](0033-derive-user-identity-only-from-validated-tokens.md), [ADR-0036](0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md), [ADR-0037](0037-protect-mcp-servers-with-network-and-workload-identity-boundaries.md), [ADR-0565](0565-derive-data-classification-from-okf-and-only-allow-raising-it.md), [ADR-0594](0594-give-the-three-experiences-the-same-mcp-tools-behind-signed-classification-markers.md), [ADR-0595](0595-set-demo-passwords-from-one-shared-value-through-one-variable-per-component.md), [ADR-0603](0603-close-the-medium-severity-security-gaps-found-in-the-2026-11-06-review.md)

## Context

A read-only review on 2026-11-06 (three parallel passes: identity, secrets and network; the AI and agent surface; supply
chain and GitOps) looked for **conceptual** weaknesses a customer running this platform would inherit, not for
vulnerable library versions. Versions are current. The platform's design is strong where it is written down (the
five-factor tool policy, per-user identity propagation, HMAC-signed classification markers, read-only Kubernetes tools)
and **permissive by default where it was built for a demonstration**: the controls exist, but many are in observe mode,
off, or scoped to everything.

This ADR holds the findings that break a trust boundary. The medium-severity findings are in ADR-0603.

**Limits of the review.** It read code and charts; nothing was replayed on a cluster. Every `file:line` below must be
re-read before it is fixed. `agent-runtime` and `agent-frontend` carry no sources in this repository and were not
audited. The UnifAI `net_guard` and `OUTBOUND_ALLOWED_HOSTS` code lives in another repository and was not reviewed.
`docs/security/ai-security.md` and `threat-model.md` are three-line stubs, so the review had no stated threat model to
test against (see the last clause).

### Findings

| # | Finding | Evidence | Attack a customer faces |
|---|---|---|---|
| C1 | Vault is a single point of total compromise: one key share and threshold, the unseal key and root token kept together in a cluster Secret, the listener without TLS, the `file` backend | `ansible/roles/vault/tasks/install.yml:103-121`, `gitops/charts/vault/values.yaml:32-36` | `get secret` in `zuno-vault`, or an etcd backup, yields every secret. Nothing is sealed against the cluster it runs in |
| C2 | One `ClusterSecretStore` reads all of `zuno/data/*` for any namespace | `gitops/charts/external-secrets/templates/clustersecretstore.yaml`, policy `eso-reader` in `ansible/roles/vault/kustomize/unseal-configure/configmap.yaml:40-46` | Whoever may create an `ExternalSecret` anywhere reads the Keycloak admin password, the database roots and the OIDC secrets |
| C3 | Istio issues workload identities but enforces none: no `PeerAuthentication`, no `AuthorizationPolicy` | `gitops/charts/service-mesh/README.md:58-61` | Plaintext callers are accepted and no service checks `source.principal`. NetworkPolicy is the only barrier |
| C4 | ArgoCD is cluster-admin, the AppProject allows every kind in every namespace, 106 Applications follow `main` with prune on, and one chart repository is plain HTTP | `ansible/roles/argocd/kustomize/appproject/appproject.yaml:13-22`, `gitops/root-app-of-apps.yaml:21-28` | A merge to `main`, or a tampered chart in transit, becomes a cluster takeover |
| C5 | One shared password feeds Keycloak root, AAP, 15+ database roots and every persona; the fallback is `md5(org:env:seed)`; the realm has no brute-force protection, password policy or OTP; four clients allow the password grant | `ansible/inventories/demo/group_vars/all/passwords.yml:28-72`, `gitops/charts/keycloak/files/realm-zuno.json` (`directAccessGrantsEnabled` on `openshift`, `aap`, `zuno-evaluations`, `zuno-stresstest`) | One leaked credential opens the platform; guessing is unthrottled |
| C6 | ai-gateway and mcp-gateway accept any token the realm signs (`JWT_AUDIENCE` unset means no `aud` check); Authorino fetches JWKS over HTTP and pins no issuer or audience | `components/ai-gateway/app/auth.py:33,133-136`, `components/mcp-gateway/app/auth.py:36,79-82`, `gitops/charts/connectivity-link/values.yaml:90` | A token minted for `aap` or `openshift` (both allow the password grant) is replayed against the gateways |
| C7 | Guardrails observe and fail open: the minimum mode is `observe`; a detector outage lets the request through even in `block`; streams are never blocked; only the last user message is scanned, not tool results or RAG text; the built-in detector is eight regular expressions | `zuno-demo-agents/policies/guardrails/guardrails-policy.yaml`, `components/ai-gateway/app/guardrails.py`, `components/ai-gateway/app/main.py` (`_observed_stream`) | Indirect injection planted in a Confluence page or a crawled web page is read as a tool result and is never inspected |
| C8 | Quota is bypassed on the Anthropic and Responses paths: `/v1/messages` is served by MaaS and the token limits do not apply to it | WP-220 live findings (about 72,000 tokens, no decrement) | An API key on that path consumes without a ceiling. WP-220 and the Claude Code key treat this as intended, so the answer is **metering**, not blocking |
| C9 | Shared service identities act for every user: Dify and the token proxy use one identity; the Confluence, Salesforce and git-forge servers use one credential and do not scope arguments to the caller; the user's bearer is forwarded unchanged to every downstream MCP server | `components/zuno-dify-knowledge/app/main.py`, `components/zuno-token-proxy`, `components/mcp-servers/confluence/server.py:242`, `components/mcp-gateway/app/downstream.py` | Confused deputy: a user, or an injected agent, reads or writes beyond their own scope; a logging downstream server can replay the bearer |
| C10 | Classification is declared by the caller (`X-Zuno-Data-Classification`, default C1); signed markers fail closed only for two client families | `components/ai-gateway/app/main.py:349`, ADR-0594 | C3 content labelled C1 reaches a SaaS model. **Already owned by ADR-0565 clause 5 and WP-209.** This ADR adds nothing to it except the marker default below |

## Decision

**The platform adopts a secure-by-default baseline for every boundary above, and keeps the permissive demo behaviour only
as an explicit, named profile (WP-227).** Each clause is delivered by the work package named after it.

1. **Vault (C1, WP-223).** Auto-unseal through an AWS KMS key the cluster does not hold, used by a dedicated IAM
   identity limited to `kms:Encrypt`, `kms:Decrypt` and `kms:DescribeKey` on that key. This is a second
   human-supplied credential next to the one ADR-0024 allows, accepted because nothing inside the cluster can unseal
   Vault. The initial root token is used once over exec, revoked after bootstrap and never stored in a cluster Secret;
   the configure Job and every Ansible seed log in through Kubernetes-auth roles (`vault-configurator`,
   `ansible-seeder`) with one-hour tokens. Recovery keys are handed to the operator outside the cluster. Raft storage
   in place of `file`. Listener TLS on, with an OpenShift service-CA certificate (no dependency on Vault's own PKI).
   The UI Route is off by default. An existing Vault moves through a scripted in-place migration.
2. **Secret reach (C2, WP-223).** No `ClusterSecretStore`. One `SecretStore` per namespace, each with its own Vault
   role and a policy listing the exact keys the namespace reads, all taken from one table
   (`platform/vault/secret-access.yaml`) that a check enforces. Whoever may create an `ExternalSecret` in a namespace
   reaches only that namespace's keys.
3. **Passwords (C5, WP-223).** A `zuno_security_profile` (`demo` or `hardened`) selects the scheme. In `hardened`
   every infrastructure credential gets its own random value from Vault, the `md5(org:env:seed)` fallback fails
   instead of guessing, and the shared persona value never feeds an infrastructure credential; the realm also gets a
   password policy, a one-hour idle session and OTP for the console administrator. Both profiles get temporary
   brute-force protection, applied to live realms by the reconcile Job. `directAccessGrantsEnabled` stays on for
   `openshift` and `aap` **by decision of 2026-11-06**: headless `oc login` with a Keycloak password is kept.
4. **Mesh (C3, WP-224).** `PeerAuthentication` STRICT mesh-wide, with the existing PostgreSQL and MariaDB exceptions
   written down per port. A deny-by-default `AuthorizationPolicy` per namespace keyed on SPIFFE principals.
5. **GitOps (C4, WP-224).** The AppProject lists the kinds it may create, the controller loses the blanket
   `cluster-admin` binding, `main` requires reviews and signed commits, charts come over HTTPS and by digest, and
   stateful resources carry `Prune=false`.
6. **Audience (C6, WP-222 and WP-224).** ai-gateway and mcp-gateway require the audience `zuno-admin-api`, the one
   every experience client already carries through the `maas-gateway-audience` mapper and that a2a-gateway already
   requires; `JWT_AUDIENCE_REQUIRED=true` makes a gateway refuse to start without one (WP-222). Authorino reads JWKS
   over HTTPS and pins `iss` and `aud` (WP-224).
7. **Admin routes (WP-222).** `/admin/*` on ai-gateway and mcp-gateway needs a valid token whose groups include
   `ADMIN_GROUPS` (default `ocp-paas-ops`, `ocp-ai-ops`). `ADMIN_AUTH_MODE=off` is the visible opt-out.
8. **Guardrails (C7, WP-225).** In `block` mode a detector outage fails closed for classes C2 and above. Tool results and
   RAG text are scanned before they reach the model. Streamed replies are buffered, or cut, when a detection lands. A
   model-based injection classifier joins the regular expressions.
9. **Metering (C8, WP-225).** The `/v1/messages` and `/v1/responses` paths are metered in the ai-gateway, or through a
   Limitador data-extraction rule, so a per-key ceiling exists. They are not blocked.
10. **Delegated scope (C9, WP-225).** Shared-credential MCP servers check the caller's groups against a space, repository
    or recipient allowlist passed as signed context. The mcp-gateway exchanges the user token (RFC 8693) or signs a
    per-call assertion instead of forwarding the bearer. Dify and the token proxy authenticate their callers.
11. **Classification (C10).** Delivered by ADR-0565 and WP-209. The marker fail-closed list (`MARKER_FAIL_CLOSED_CLIENTS`)
    covers every experience client by default.
12. **Profile (WP-227).** A `hardened` profile activates clauses 1 to 10 in one switch for a customer deployment. The
    demo profile keeps today's behaviour and says so in its name. A check fails when a hardened install has any clause
    off.
13. **Threat model.** `docs/security/threat-model.md` and `ai-security.md` stop being stubs: each of C1 to C10 gets an
    entry with its attacker, its asset and the clause that closes it.

## Alternatives considered

- **Document the gaps and ship as is.** The ADR trail already does this for several of them. A customer does not read
  an ADR before the install; the default has to be safe. Rejected.
- **Harden the demo itself.** Single-share Vault, shared passwords and a permissive mesh exist so that a rehearsal
  restarts quickly (ADR-0345, ADR-0595). Making them strict makes the demo slower to recover. A separate profile keeps
  both properties. Retained as clause 12.
- **Block `/v1/messages`.** Closes the quota bypass at once but removes the Claude Code path WP-220 verified on purpose.
  Rejected in favour of metering.
- **One ADR per finding.** Ten records for one review, with no shared profile. Rejected.

## Consequences

- A hardened install is slower to bootstrap (an external KMS, per-namespace stores, mTLS everywhere) and every new
  service needs an `AuthorizationPolicy` and a Vault role before it works.
- Clause 6 refuses every token without `zuno-admin-api`. On 2026-11-06 the live realm and seven days of gateway metrics showed no caller without it; a new client must get the mapper before it calls a gateway.
- Turning clause 7 on breaks any runbook that calls `/admin/*` without a token. No script in this repository does.

## Security considerations

Each clause removes a path from "one foothold" to "whole platform": C1 and C2 (any secret), C3 and C6 (any service), C4
(the cluster), C5 (the identity provider), C7 to C9 (the model, and the data it can reach). Negative tests are required for
clauses 6, 7, 9 and 10: a token with the wrong audience is refused, a non-admin token on `/admin/*` is refused, a metered
path past its ceiling is refused, a tool call outside the caller's allowlist is refused.

## Operational considerations

Roll out in the order of the work packages. Rehearse WP-223 and WP-224 on demo333 only with the user's go for each
cluster action. Keep the Vault re-seal runbook until auto-unseal is proven across a restart. Re-run the review after each
package; a finding is closed when it is replayed, not when its package merges.

## Work packages

WP-222 (quick wins, shared with ADR-0603), WP-223, WP-224, WP-225, WP-227.
