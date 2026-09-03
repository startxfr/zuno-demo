# WP-091: Reconcile Keycloak clients, and provision zuno-admin-api (promotes ADR-0530)

- **State:** Done (2026-08-28) - live-verified; `GET /api/colleagues` returns 200
- **ADRs:** ADR-0530 (Proposed -> Implemented after this WP and a live run)
- **Depends on:** nothing new. Uses the existing `keycloak-admin` Secret, the existing `vault-secrets` projected volume, and `ansible/roles/vault`'s seeding pattern.
- **Blocks:** ADR-0527's live two-persona pass (WP-088/WP-089 cannot be exercised at all while `GET /api/colleagues` and `GET /api/groups` return 503), and ADR-0213's long-standing "trust boundary unprovisioned" caveat.
- **Estimated files touched:** ~12

> Execute this brief as a standalone task from the repository root.
>
> Tracked in [docs/roadmap/implementation-roadmap.md](../implementation-roadmap.md) Phase 21.

## Goal

Make `gitops/charts/keycloak/files/realm-zuno.json` authoritative for clients,
and use that new mechanism to provision `zuno-admin-api` - the confidential
client ADR-0213 specified, ADR-0527 extended with `query-groups`, and no work
package has ever been able to deliver, because editing the realm file does not
reach a live realm.

## ADR references

Primary: [docs/adr/0530-reconcile-keycloak-clients-instead-of-relying-on-a-create-only-realm-import.md](../../adr/0530-reconcile-keycloak-clients-instead-of-relying-on-a-create-only-realm-import.md)
(read fully - Decision 4's scope boundary is the clause most likely to be
over-implemented).

Read also: [ADR-0213](../../adr/0213-introduce-role-based-conversation-sharing.md)
(the colleague-lookup trust boundary and its least-privilege role list),
[ADR-0527](../../adr/0527-introduce-the-project-as-the-sharing-and-context-boundary.md)
(why `query-groups` is needed on top), and
[ADR-0313](../../adr/0313-move-day1-schema-jobs-and-llm-provider-secrets-behind-argocd.md)
(the Sync-hook-not-PreSync rule and the fail-loudly posture this Job copies).

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0 and ADR-0530 is in the index.
- Confirm the premise still holds rather than trusting this brief:

      oc get job zuno-realm -n zuno-auth \
        -o jsonpath='{.spec.template.spec.containers[0].args}{"\n"}'
      # expect: [...,"--override=false"]

      oc get keycloakrealmimport zuno-realm -n zuno-auth \
        -o jsonpath='{.metadata.generation}{"\n"}'
      # > 1 means the realm spec changed after the one import that ran

- `oc exec -n zuno-auth zuno-0 -- ls /opt/keycloak/bin/kcadm.sh` succeeds.
  There is no `curl` in that image; do not write the Job around one.

## Scope

1. **Declare the client.** Add `zuno-admin-api` to `realm-zuno.json`:
   confidential, `serviceAccountsEnabled: true`, standard/implicit/direct-access
   flows all off, no redirect URIs, `"secret": "${vault.admin_api_client_secret}"`.
   Add the matching `users[]` entry `service-account-zuno-admin-api` carrying
   `serviceAccountClientId` and `clientRoles: {"realm-management": ["view-users",
   "query-users", "query-groups"]}` - never `manage-users` (ADR-0530 clause 5).

2. **Seed and deliver the secret.** A `vault_seed_if_missing` task at
   `keycloak/zuno-admin-api-client`, following the `aap`/`openshift` blocks in
   `ansible/roles/vault/tasks/install.yml` exactly. A
   `zuno-admin-api-client-secret` ExternalSecret in the keycloak chart, and the
   matching entry in `keycloak.yaml`'s `vault-secrets` projected volume at path
   `zuno_admin__api__client__secret` - single underscores silently fail every
   lookup, see that block's own comment.

3. **The reconcile Job.** A `Sync` hook in the keycloak chart, sync-wave after
   the realm import, running `kcadm.sh` from the Keycloak image against the
   live realm. Reads the client list from a ConfigMap rendered from the same
   `files/realm-zuno.json` (the `.Files.Get` pattern
   `gitops/charts/rag-service/templates/configmap-schema.yaml` already
   establishes). Create-or-update per client; then apply service-account role
   mappings from the `users[]` entries. `set -euo pipefail`,
   `activeDeadlineSeconds`, `hook-delete-policy: BeforeHookCreation`.
   **Clients only** - see ADR-0530 clause 4 and log the boundary on every run.

4. **Wire agent-bff.** `KEYCLOAK_ADMIN_BASE_URL`, `KEYCLOAK_ADMIN_CLIENT_ID` and
   `KEYCLOAK_ADMIN_CLIENT_SECRET` on the `bff` container in each agent chart
   that serves projects, the secret via ExternalSecret from
   `keycloak/zuno-admin-api-client`. `config.Config` and `NewAdminClient`
   already read these and already fail closed when any is empty - no Go change
   should be needed, and if one seems to be, re-read `main.go` first.

5. **Tests.** A rendering test that the Job, ConfigMap, ExternalSecret and the
   projected-volume entry all appear and agree on names; and a check that the
   realm file's declared service-account roles never include `manage-users`.
   Follow the standalone-script convention, not pytest.

## Out of scope

- Reconciling groups, users, realm roles, IdPs or realm settings (ADR-0530
  clause 4). If a group description is wrong, this WP does not fix it.
- Changing the realm import itself.
- The ADR-0527 two-persona acceptance pass. This WP unblocks it; it does not
  run it.

## Acceptance

- `helm lint gitops/charts/keycloak` and `helm template` render the four new
  resources with consistent names.
- On a live run: the reconcile Job succeeds, `zuno-admin-api` exists in the
  realm with exactly the three `realm-management` roles and no others, and a
  second sync is a clean no-op (idempotence is the whole point).
- `GET /api/colleagues` and `GET /api/groups` return 200 for an entitled
  persona instead of 503.
- `python3 platform/docs/check_docs.py` exits 0.

## Operator follow-up

Keycloak is shared infrastructure. The live run mutates the realm and must be
agreed before it is triggered, not folded into a routine sync.
