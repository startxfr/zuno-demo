# ADR-0530: Reconcile Keycloak clients instead of relying on a create-only realm import

- **Status:** Implemented (2026-08-28) - live-verified. The reconcile Job created
  `zuno-admin-api` and merged into the ten existing clients; its service account
  holds exactly `view-users`/`query-users`/`query-groups`; the client-credentials
  grant succeeds against the KC_VAULT-resolved secret, reads 3 users and 19
  groups, and is refused `POST /users` with 403. `GET /api/colleagues` now
  answers **200** through agent-bff, ending the 503 that had stood since WP-066.
  `GET /api/groups` still 404s, which is WP-088's pending rebuild and not this
  ADR: the deployed agent-bff image was built 19:27Z and the commit adding that
  route landed 20:28Z
- **Target:** v0.4
- **Date:** 2026-08-28
- **Decision owners:** Zuno Demo architecture team

## Context

`gitops/charts/keycloak/files/realm-zuno.json` reads like the authoritative
description of the `zuno` realm. Every ADR that has needed a new Keycloak
client has edited it and considered the job done: ADR-0320 (`openshift`),
ADR-0326 (the confidential agent frontends), ADR-0354/WP-072 (`aap`).

It is not authoritative. The Keycloak operator renders that file into a
`KeycloakRealmImport` CR and runs it with **`--override=false`**, and the
`KeycloakRealmImport` CRD exposes no field to change that (`keycloakCRName`,
`labels`, `placeholders`, `realm`, `resources` - checked against the installed
CRD on 2026-08-28). An import against an existing realm is therefore skipped.
The operator also does not re-run the import when the CR's realm changes.

Measured live on 2026-08-28:

| Signal | Value |
|---|---|
| Import Job args | `kc.sh --verbose import --file=... --override=false` |
| Import Job created | `2026-08-24T22:22:02Z`, never recreated |
| `KeycloakRealmImport` `generation` | `2` - the realm spec changed since |
| `zuno-keycloak-d1` | `Synced` / `Healthy` at `e5f6bcee`, `Succeeded` |

So ArgoCD faithfully delivers new realm content into the CR, the operator sees
it, and nothing is applied. The realm has been frozen since its one import.

The `aap` client works live only by calendar coincidence: it was committed on
2026-08-24 at 19:46 and the realm was imported at 22:22 the same evening. The
case that actually matters - adding a client to an *already live* realm - has
never been exercised. The one realm edit made since (`de1524e1`, 2026-08-26,
the `sales`/`adv` group descriptions) is live, but it reached the realm through
a hand-run Admin REST call, not through this chart.

This is why `zuno-admin-api` - specified by ADR-0213, inherited by ADR-0527,
and blocking `GET /api/colleagues` and `GET /api/groups` with a 503 that makes
the project RBAC tab unusable - has sat as an unexplained "operator step"
across two work packages. The mechanism to provision it did not exist. Adding
it to the realm file would have changed nothing and looked like it should.

## Decision

1. **The realm import keeps its current role: first creation only.** It is not
   a bug to be fixed here - `--override=true` on a live realm is a blunt
   instrument that would rewrite users, sessions and credentials, and the CRD
   does not offer the knob anyway. It stays exactly as it is.

2. **A new `Sync`-hook Job, `zuno-keycloak-client-reconcile`, reconciles
   clients from the same `files/realm-zuno.json`** against the live realm on
   every sync, using `kcadm.sh` from the Keycloak image itself (already
   present; no new image, no new toolchain). For each declared client it
   creates the client if absent and updates it in place if present. The file
   becomes authoritative for the thing it is most often edited to change.

3. **Service-account role mappings are declared in the same file**, as `users[]`
   entries named `service-account-<clientId>` carrying `serviceAccountClientId`
   and `clientRoles` - the representation a real Keycloak realm export already
   uses. The file stays a valid realm export, and the reconcile Job needs no
   second, parallel source of truth to consult.

4. **Scope is clients and their service-account role mappings. Nothing else.**
   Groups, users, realm roles, identity providers, client scopes and realm
   settings remain create-only and are *not* reconciled. This boundary is
   deliberate: reconciling users would fight runtime state (sessions, consents,
   credentials), and reconciling groups would silently revert the kind of live
   correction `de1524e1` records. A mechanism that reconciles half a realm
   while looking like it reconciles all of it is a worse trap than the one this
   ADR removes, so the Job logs the boundary explicitly on every run and this
   clause is the place that defines it.

5. **`zuno-admin-api` is the first client provisioned this way**, and the
   realm's first client-credentials client. Confidential;
   `serviceAccountsEnabled: true`; standard flow, implicit flow and direct
   access grants all **off** (it is never a login client); no redirect URIs.
   Its service account holds exactly three `realm-management` client roles -
   `view-users`, `query-users`, `query-groups` - and never `manage-users`.
   `query-groups` is what ADR-0527's `GET /api/groups` needs beyond what
   ADR-0213 originally specified.

6. **Its secret follows the established path**: Vault-seeded at
   `keycloak/zuno-admin-api-client` by `ansible/roles/vault`, delivered to
   Keycloak as `zuno_admin__api__client__secret` through the existing
   `vault-secrets` projected volume, and referenced in the realm file as
   `${vault.admin_api_client_secret}` so Keycloak's file vault provider
   resolves it at use time - identical in every respect to `openshift` and
   `aap`. agent-bff receives the same value from Vault through its own
   `ExternalSecret` as `KEYCLOAK_ADMIN_CLIENT_SECRET`.

7. **The Job fails loudly.** `set -euo pipefail`, `activeDeadlineSeconds`, and
   a non-zero exit on any `kcadm.sh` failure, so a broken reconcile fails the
   sync rather than reporting green - the same posture ADR-0313 settled on for
   the schema-apply Job after the 2026-08-14 incident.

## Alternatives considered

- **`--override=true` on the realm import.** Not offered by the CRD, and
  destructive if it were: a full realm import over a live realm rewrites user
  credentials and drops runtime state. Rejected on both counts.
- **Delete the realm and re-import.** Would provision the client, and would
  also invalidate every session and re-hash every demo persona password. A
  one-off manual act dressed as automation; the next client would need it
  again. Rejected.
- **Create `zuno-admin-api` by hand and document it.** Fastest path to
  unblocking ADR-0527, and the shape this platform has silently been using.
  Rejected because it leaves the realm file inert and the next client in the
  same position - the specific failure this ADR exists to end.
- **A generic "reconcile the whole realm" Job.** Tempting, and wrong for the
  reasons in Decision 4: users and groups carry runtime state that a
  declarative file should not be reverting behind an operator's back.
- **`kcadm.sh` vs a Python/`curl` script against the Admin REST API.** `kcadm.sh`
  ships in the Keycloak image, handles token acquisition and refresh, and needs
  no new image to maintain. The `curl` route would have needed a new image with
  `curl` and `jq` - the running Keycloak image has neither (verified
  2026-08-28: `curl: command not found` inside `zuno-0`).

## Consequences

- `realm-zuno.json` becomes authoritative for clients, and only for clients.
  Editing a client there now reaches a live realm; editing a group there still
  does not. Decision 4 is the contract, and the divergence is real - anyone
  reading the file needs to know which half of it is live.
- Hand-patched client configuration is reverted on the next sync. That is the
  intent, but it is a behavior change: live client edits were previously
  permanent.
- The Job holds Keycloak admin credentials, which the schema-apply precedent
  does not. It runs in `zuno-auth`, mounts the existing `keycloak-admin`
  Secret, and is the only workload besides Keycloak itself to read it. This is
  a new privilege concentration and is called out here rather than buried.
- ADR-0213's and ADR-0527's "unprovisioned trust boundary" caveat can be
  retired once WP-091 runs live; the 503 fail-closed paths in `agent-bff` and
  the frontend stay as they are, because a reconcile failure must still
  degrade rather than break.
- Nothing here changes how a *fresh* install behaves: the import still creates
  the realm, and the reconcile Job then finds every client already correct.
- A pre-flight diff of the ten live clients against what this chart renders
  found no substantive drift: identical scopes, identical mappers, identical
  attributes, and every stored client secret still the `${vault.*}` placeholder
  the import wrote. The first reconcile is therefore expected to create exactly
  one client and change nothing else. That also means the point-in-time mirror
  `ansible/roles/mlops` keeps of each `<agent>-frontend-client-secret` does not
  go stale as a result of this change.

## Dated progress notes

### 2026-08-27/28 - what the first live run actually cost

Three things went wrong that the repository-side work had not anticipated. All
three are now guarded; they are recorded because each was cheap to prevent and
expensive to diagnose at two in the morning.

**`kcadm update -f` does not merge.** Caught before the run, by diffing the ten
live clients against what the chart renders rather than trusting it. Decision 2
carries the detail. Had it not been caught, the Job would have gone green while
stripping the `groups` claim mappers off every client, and the failure would
have surfaced somewhere far from its cause.

**`CLIENT.DESCRIPTION` is `varchar(255)`.** The first run updated all ten
existing clients and then failed creating `zuno-admin-api` on a 283-character
description. The Admin API answers a bare `[unknown_error]`; the real cause -
`value too long for type character varying(255)` - appears only in the Keycloak
server log. The create rolled back cleanly, leaving no half-made client.
`test_client_text_fields_fit_keycloak_s_columns` now checks every declared
client. Note `soursage-frontend` sits at 251 characters, so the margin is thin
by accident rather than by design.

**A failing hook pins the whole sync to its revision.** After the fix was
pushed, ArgoCD kept retrying the *old* operation - `retry.limit: 5`, each
attempt burning the Job's own `backoffLimit` - and each retry re-applied the
ConfigMap at the stale revision, so the fix could not land while the failure
caused by that fix's absence was still being retried. It resolves itself once
the retries exhaust (about 25 minutes here), but the shape is worth knowing:
`status.sync.revision` can already show the new commit while
`operationState.operation.sync.revision` is still the old one, and the second
is the one that decides what gets applied.
