# WP-192: One demo password, one variable per component, and named Keycloak administrators

- **State:** Repo work merged (2026-11-03: phases 1 and 2 pushed, phase 3 applied on demo333; the Jobs' second run as `zuno-automation` and the database/twin follow-ups remain)
- **ADRs:** [ADR-0595](../../adr/0595-set-demo-passwords-from-one-shared-value-through-one-variable-per-component.md)
- **Depends on:** none
- **Related:** [ADR-0349](../../adr/0349-restructure-demo-personas-cluster-access-groups-and-new-agents.md) (section 3 amended), [WP-190](wp-190-one-identity-one-budget-and-one-infrastructure-pattern-for-the-three-experiences.md) (the Keycloak plumbing it declared once)
- **Target:** v0.13
- **Estimated files touched:** ~14 (group_vars, the vault role, the Keycloak chart Jobs and ExternalSecrets, two roles, docs, one test)

> Why: the Keycloak console shows "logged in as a temporary admin user"; the whole automation signs in with that bootstrap
> account, so it cannot simply be removed. The user also wants every human-facing demo password on one value, kept out of the
> public repository, with one variable per component so any of them can change later without a refactoring.
> User decisions of 2026-11-03: value only in `ansible/confidential.yml`; deterministic generated fallback of 22 characters;
> scope admins, personas by family, databases and caches; code first, live on demo333 step by step; dedicated
> `zuno-automation` user, named `zuno-admin`, bootstrap `admin` disabled at the end; databases on fresh installs only.

## Goal

One shared password reaches every admin, persona family and database through its own variable. The Keycloak automation runs as
`zuno-automation`, humans sign in as `zuno-admin`, and the temporary bootstrap account is disabled.

## Steps

1. **Variable scheme (phase 1).** `ansible/inventories/demo/group_vars/all/passwords.yml`; the literals removed from `main.yml`
   and `auto.yml`; `confidential.example.yml` documented; `platform/vault/tests/test_password_scheme.py` renders it with ansible.
2. **Keycloak accounts (phase 2).** New Vault paths `keycloak/console` and `keycloak/automation`, their ExternalSecrets, the
   client-reconcile Job ensures the two master users (login as `zuno-automation`, else the bootstrap account), the other Job and
   both roles switch to `keycloak-automation` (shared task `ansible/tasks/read_keycloak_automation_credentials.yml`, bootstrap
   admin as fallback); the OpenClaw Control UI password reads its own variable. The `eval-*`/`stress-*` twins keep sharing
   `demo-personas-password` (five consumers); splitting them is a follow-up.
3. **Live on demo333 (phase 3).** Each cluster action with the user's go: seed the new paths, wait for the Secrets, check the
   Jobs and roles as `zuno-automation`, sign in as `zuno-admin`, disable the bootstrap `admin`, re-seed the personas path.
   Databases are not rotated live (ADR-0529).

## Acceptance

- `python3 platform/vault/tests/test_password_scheme.py` passes; no password literal in `git grep` outside ADR history.
- Live: master realm has `zuno-admin` and `zuno-automation`, the bootstrap `admin` is disabled, the client-reconcile and
  persona Jobs are green as `zuno-automation`, and the console shows no temporary-admin warning for `zuno-admin`.

## Live on demo333 (2026-11-03)

- `zuno-admin` and `zuno-automation` exist in the master realm (created by the client-reconcile Job at 83cd2bb0), both with the
  `admin` role, and both sign in with the shared demo password (password-grant 200). The bootstrap `admin` is disabled, not deleted.
- Vault `keycloak/console` and `keycloak/automation` were seeded by `make d0 install vault` (only the missing paths were written).
  `zuno/keycloak/demo-personas` was overwritten with the shared persona password, `demo-personas-password` and
  `zuno-ai-run/ragas-eval-credentials` were force-refreshed, and the passwords of all 37 realm users (27 humans, 5 `eval-*`,
  5 `stress-*`) were reset with `kcadm`; password-grant logins as `consultant-01`, `eval-consultant-01` and `stress-sale-01` return 200.
- Not done: databases and caches keep their current passwords (ADR-0529; the new values apply to fresh installs; the per-role
  PostgreSQL procedure is in `docs/platform/operations.md`, MariaDB/Redis/AAP databases are not covered). The
  `eval-*`/`stress-*` twins still share the humans' Secret: at least eight consumers read `DEMO_PERSONA_PASSWORD` from it (the
  acceptance gate, the stresstest, failover and persona probes, the mlops copy, the RAGAS ExternalSecret, the scaffold and compare
  scripts) and pick the twin family by `EVAL_TWIN_PREFIX`, so a split is a decision to take, not a quick follow-up. The first run of the reconcile Job used the bootstrap admin (the
  automation account did not exist yet); a second run as `zuno-automation` has not been observed.
