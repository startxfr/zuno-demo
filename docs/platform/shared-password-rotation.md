# Runbook: rotating the shared demo password

On the `demo` security profile (ADR-0602), two values are shared by many accounts: the **personas value**
(`zuno_personas_mainpwd`) and the **admin value** (`zuno_admin_mainpwd`). On a demo cluster they can be the same
string. Rotate them when a value is exposed, when someone who knew it leaves, or before a cluster is opened to new
users. This runbook covers the whole family except the database and Redis roles, which have their own procedure
([Moving a PostgreSQL role onto the shared demo password](operations.md#moving-a-postgresql-role-onto-the-shared-demo-password-adr-0595-adr-0529)).

Never write a value in a chat, a commit, a document or a command line that is echoed. Values travel on stdin or in
mode-600 files in a private state directory, and are deleted at the end.

## What the value protects

| Family | Where it lives | How it is changed |
|---|---|---|
| Realm personas (`zuno` realm) | Keycloak, Vault `keycloak/demo-personas`, Secret `zuno-auth/demo-personas-password` | `kcadm set-password`, then Vault |
| Twins (`eval-*`, `stress-*`) | Keycloak | Reset by the hook Job `job-eval-personas` on the next sync of `zuno-keycloak-d1`, from the Secret above |
| Keycloak master accounts | Vault `keycloak/console`, `keycloak/automation` | `kcadm` first, then Vault |
| Dify admin | Vault `dify/admin` | Dify itself (`flask reset-password`), then Vault |
| AAP admin | Vault `aap/admin` | Check first whether it holds the value at all (step 1 of the preparation) |
| Copies of the personas value | acceptance-gate, demo-persona-probe, stress-test, failover and OpenClaw UI Secrets | Refreshed from Vault, see "Copies" |
| Database and Redis roles, MariaDB, the Red Hat account behind `aap-rhn-credentials` | | Not rotated here. The Red Hat account is the owner's, changed on the Red Hat side |

On the demo profile `paas-ops-01` signs in to OpenShift through Keycloak and is `cluster-admin`. If the personas value
is exposed, treat it as a cluster-admin credential.

## Before the window

1. **Read, do not print.** Find out which Secrets hold which value with a yes/no comparison (a script that exits 0 or 1).
   This decides the scope: on some clusters the AAP admin never held the shared value (a sign-in with it answers 401), so there
   is nothing to rotate there.
2. **Generate the new values** on the operator's machine, letters and digits only, 20 characters or more (some database
   passwords end up unencoded in connection URIs, and the hardened profile asks for a digit):
   `umask 077; tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24 > <state-dir>/new-personas`. Never `cat` the file.
3. **List the realm users** (`kcadm get users -r zuno -q max=500 --fields username`). Expect the personas, the fixtures
   and the twins. Any extra user is a question for the owner.
4. **Baseline.** `make demo golden-path` and `make d3 check recovery` must be green. Peers must not hold a window, and
   operators must not be restarting.
5. **Suspend the clients that sign in with the old value** for the window (RAGAS evaluation, stress-test and failover
   Jobs, acceptance-gate runs), so that they do not trip the brute-force limit.
6. **Announce the window** to every peer session. Keycloak is the SSO of everything: expect 1 to 2 minutes of failed
   sign-ins at the cut-over.
7. **Compromise assessment**, if the rotation answers an exposure: API audit by the powerful users, `oc get users,identities`,
   new ClusterRoleBindings, ServiceAccounts, OAuthClients, ExternalSecrets reading `keycloak/*`, and Keycloak events
   (usually off on the demo profile). The audit log rotates within minutes to hours, so a rotation does not prove that
   nothing happened. Write down what cannot be known.

## Phase 0: containment

Reset first the accounts that give the most power, from a `kcadm` session on `master` as `zuno-automation` with its
current password:

1. `kcadm set-password -r zuno --username <user> --new-password "$(cat <state-dir>/new-personas)"` for `paas-ops-01`,
   `ai-ops-01` and `ai-dev-01`, then log each out (`kcadm create users/<id>/logout -r zuno`).
2. A Keycloak reset ends no session. Delete the OpenShift OAuth tokens of the same users (`oauthaccesstokens`, and
   `oauthauthorizetokens`, filtered on `userName`).
3. `kcadm set-password -r master --username zuno-admin ...` with the admin value. Do **not** change `zuno-automation` yet.
4. Check that the old value fails and the new one succeeds on an OpenShift sign-in.
5. An access token already issued stays valid for 900 s and Authorino and the ai-gateway check it offline. Containment is
   complete 15 minutes after step 1.

## Phase 1: personas and Keycloak accounts

Order matters: **Keycloak first, then Vault and the Secret copies.** If a Secret gets the new value before Keycloak does,
the Keycloak Jobs cannot sign in. They retry past the 30-failure limit and lock the account for up to 15 minutes.

1. Reset every persona in the realm with `kcadm set-password` (non-temporary), and log each out. Go straight to Phase 2
   for `keycloak/demo-personas`: as long as `demo-personas-password` holds the old value, every consumer that reads it
   fails.
2. Twins: nothing to do here, `job-eval-personas` resets them at the next sync (Phase 3).
3. `zuno-automation` last: change it in Keycloak, then write its Vault path at once. The client-reconcile Job re-sets both
   master passwords from their Secrets on every sync, so Vault must hold the new value before the next sync of
   `zuno-keycloak-d1`.
4. kcadm traps: use `kcadm config truststore` (`config credentials --truststore` is not kept), and add `-q max=` when
   listing, because group children and users stop at 10 or 100 by default.

## Phase 2: Vault and the Secrets that follow it

1. `keycloak/demo-personas` holds only `password`, so `vault kv put` is safe. The vault role writes a path only if it is
   missing (`ansible/tasks/vault_seed_if_missing.yml`), so a re-run of the role never changes it.
2. Every other path holds more fields (`username` for `keycloak/console`, `keycloak/automation` and the database roles).
   Use **`vault kv patch -method=rw`, never `kv put`**, which replaces the whole version and drops them. Read the field
   names first, keys only.
3. Log in to Vault as `ansible-seeder` (Kubernetes auth). The server pod selector is
   `app.kubernetes.io/name=vault,component=server`: backup Job pods carry the first label too. Send the token and the value on stdin.
4. Force the ExternalSecrets to refresh (`ansible/tasks/force_externalsecret_refresh.yml`) instead of waiting up to
   one hour, and wait until the Secret holds the new value.
5. Update the local `ansible/confidential.yml` (`zuno_personas_mainpwd`, `zuno_admin_mainpwd`) with `ansible-vault edit`: the file is encrypted ([ansible/README.md](../../ansible/README.md), ADR-0603 M22), so `grep` and `sed` do not work on it. Until it holds the new
   values, no Vault or Keycloak seeding playbook may run: it would put the old value back.

## Phase 3: copies and derived passwords

| Consumer | Action |
|---|---|
| Twins | Force a sync of `zuno-keycloak-d1` (`ansible/tasks/force_argocd_sync.yml`). The keycloak role alone does not trigger it |
| `zuno-ai-run/acceptance-gate-credentials` | `make d2 check agents`: the only target that refreshes this copy |
| `zuno-mlops/acceptance-gate-credentials` | `make d2 install mlops` |
| `zuno-ai-run/demo-persona-probe-credentials` | `make demo check` |
| Stress-test and failover credentials | Refreshed by their next run; stale until then |
| OpenClaw Control UI (`openclaw/<persona>`, field `ui_password`) | `vault kv patch` only that field (the path also holds `cookie_secret`), refresh the ExternalSecret, then **delete the assistant pod**: the value is read as an env var |
| Dify admin | Change it in Dify first: `flask reset-password` in the `api` container of the pod labelled `app.kubernetes.io/name=dify,component=api`. Then `vault kv patch zuno/dify/admin`. Nothing else changes it, and `make d2 configure dify` signs in with the Vault value |

Restart workloads by **deleting their pods**. `oc rollout restart` is reverted by Argo CD selfHeal.

If you copy the personas value into several Secrets by script, use an **allowlist** of Secret names. PGO and AAP
database Secrets can hold the same string and must follow their own procedure.

## Phase 4: verification

1. One password-grant sign-in per family with the new value: a twin through `zuno-evaluations`, a persona through
   `openshift`, `zuno-automation` on master. The old value must be refused for `paas-ops-01`, a persona, a twin and
   `zuno-admin`.
2. No account locked: `kcadm get attack-detection/brute-force/users/<id> -r zuno` for the accounts used by automation.
3. **Scan every Secret** for the old value (keys only, never values). Anything left is either in the "not rotated here"
   list or a miss.
4. `make demo golden-path`, then `make demo browser`, then `make d3 check recovery`.
5. Record the evidence without values: times, users reset, paths written, results. Then delete the state directory.

## Traps

- **Lockout.** Clients that still send the old value (RAGAS, golden path, browser runs, stress and failover Jobs, `oc login`
  scripts) trip the 30-failure limit. Realm waits grow from 60 s to 15 min and are never permanent. Refresh their copies
  before running them.
- **A reset ends no session.** Realm sessions last up to 8 h idle and 10 h in all. OpenShift OAuth tokens and the
  oauth2-proxy cookies (OpenClaw, world model) survive too. Log users out and delete their OAuth tokens.
- **Keycloak restart.** If the operator restarts `zuno-0` when `keycloak-admin` changes, SSO is down for 30 to 65 s (one
  replica behind a minAvailable PDB, ADR-0101). Announce it.
- **The golden path uses real personas** (`eval-consultant-01`, `consultant-01`): run it only after Phase 3.
- **Keycloak's file-vault SPI file is unused.** Do not rely on it to change a password.
- **`ocp-ai-dev` and `ocp-ai-ops` can read the personas value** through an ExternalSecret they create in `zuno-ai-run`.
  After a departure, rotate again.

## Rollback

There is none to the old value: if it was exposed, it is compromised. Fix forward with the new value, re-running the same
phase.

## Scripted version

Phases map to a script kept outside the repository, run by the operator phase by phase and pasting each output:
`check`, `scan`, `phase0`, `personas`, `admin`, `dify`, `verify`, `cleanup`. The script prints no value, keeps its state in
a mode-700 directory, and is idempotent per phase. The 2026-11-13 run took about 20 minutes for 38 users.

## Follow-ups

- Extend `job-eval-personas` (or add a Job) so that every realm persona follows `zuno-auth/demo-personas-password`. A
  rotation then becomes: Vault, ExternalSecret, sync.
- Give the admin family its own value even on the demo profile (ADR-0595, ADR-0602).
