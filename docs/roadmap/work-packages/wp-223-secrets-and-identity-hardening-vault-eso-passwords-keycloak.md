# WP-223: Secrets and identity hardening: Vault, External Secrets, passwords, Keycloak (delivers ADR-0602)

- **State:** Not started
- **ADRs:** ADR-0602, ADR-0603
- **Depends on:** WP-222
- **Blocks:** WP-227
- **Estimated files touched:** ~25

> Execute this brief as a standalone task from the repository root. Every cluster action needs the user's go.

## Goal

Make Vault the real root of trust (C1), stop one namespace reading every secret (C2), end the shared-password scheme
outside the demo profile (C5), and harden the realm (M5, M6, M8).

## ADR references

ADR-0602 clauses 1 to 3; ADR-0603 clause 2 (M5 to M9).

## Preconditions

- Re-read `ansible/roles/vault/tasks/install.yml:103-121`, `gitops/charts/vault/values.yaml:32-36`,
  `gitops/charts/external-secrets/templates/clustersecretstore.yaml`, `ansible/inventories/demo/group_vars/all/passwords.yml`.
- Read ADR-0345 and the memory notes on Vault re-seal; keep the re-seal runbook until auto-unseal survives a restart.
- Decide the unseal backend (cloud KMS or an external transit Vault): this needs the user's choice.

## Repo changes

1. Vault: auto-unseal stanza, Raft storage, listener TLS; revoke the root token after bootstrap and drop the Secret copies.
2. External Secrets: per-namespace `SecretStore` (or `conditions.namespaces` plus a path prefix per tenant); Vault roles and
   policies per tenant; restrict `ExternalSecret` creation.
3. Passwords: per-component random values from Vault outside the demo profile; the md5 fallback raises.
4. Keycloak: `bruteForceProtected`, `passwordPolicy`, `directAccessGrantsEnabled: false` on `openshift` and `aap`, test
   clients out of production realms; a reconcile Job for realm settings (the import is create-only); the Vault UI Route
   restricted; htpasswd removed where OIDC is the only provider; session lifetimes reviewed.
5. Tests: policy tests that a tenant role cannot read another tenant's path; a chart check that no `ClusterSecretStore`
   lacks a namespace condition.

## Verification

Rehearsal on demo333 with the user's go: restart Vault and confirm it unseals alone; create an `ExternalSecret` in a
foreign namespace and confirm it is refused; confirm a password grant on `openshift` fails.
