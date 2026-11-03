# ADR-0595: Set demo passwords from one shared value through one variable per component

- **Status:** Accepted
- **Target:** v0.13
- **Date:** 2026-11-03
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0349](0349-restructure-demo-personas-cluster-access-groups-and-new-agents.md) (amended in part: section 3, the persona password), [ADR-0345](0345-make-self-generated-vault-credentials-idempotent.md) (seed-only-missing stays), [ADR-0529](0529-stop-the-pgo-external-secrets-write-loop-on-pguser-secrets.md) (database rotation stays out of scope), [ADR-0041](0041-remove-nominative-demo-identities-and-static-passwords-from-git.md), [ADR-0025](0025-keep-sensitive-and-real-commercial-data-outside-the-public-repository.md)

## Context

Passwords were set three different ways. `zuno_admin_password` fed only three secrets (the application database role, the
Keycloak admin and the Keycloak database role); every other `zuno_admin_*` variable that the vault role reads was defined
nowhere, so AAP, MariaDB, Redis and the other databases got a random value that the operator never knew. The weak default of
`zuno_admin_password` and the persona default were literals committed to a public repository.

On 2026-11-03 the Keycloak console showed "logged in as a temporary admin user". The live master realm has one user, the
bootstrap `admin`, and every Job and role that talks to Keycloak (`job-client-reconcile`, `job-eval-personas`,
`open_webui/keycloak_admin_group.yml`, `openclaw/keycloak_sa_groups.yml`) signs in with it. Removing it breaks all four.

The user wants one demo password for every human-facing account, while any component, persona family or service can be given
another value later without a refactoring.

## Decision

1. **One shared value, outside git.** `zuno_admin_mainpwd` and `zuno_personas_mainpwd` live in `ansible/confidential.yml`
   only (ADR-0025, ADR-0041). The repository carries no password literal.
2. **One variable per component, inheriting.** `ansible/inventories/demo/group_vars/all/passwords.yml` defines a variable for
   every Vault-seeded password in scope (Keycloak bootstrap, console and automation accounts; AAP; the PostgreSQL roles;
   MariaDB; Redis; the MLOps and Trillian databases) as `{{ zuno_admin_password | default(<generated>, true) }}`, and one per
   demo-persona family (humans, `eval-*`, `stress-*`, OpenClaw UI) as `{{ zuno_personas_password | default(<generated>, true) }}`.
   A component is changed by setting its own variable in `confidential.yml`; nothing else moves.
3. **A generated fallback, never a literal.** With no shared value (or an empty one) the default is the first 22 hexadecimal
   characters of `md5("<org>:<env>:<extra>:<component>")`. It is the same on every run, so a play never disagrees with the
   value it seeded, differs per component, and moves to another series with `zuno_password_seed_extra`. It is guessable by
   someone who knows the seed; this is accepted for a demo and the shared value is expected to be set.
4. **Machine secrets stay random.** OIDC client secrets, cookie keys and workload tokens are typed by nobody and keep the
   vault role's random generation.
5. **Named Keycloak administrators.** Two permanent accounts are created in the master realm by the client-reconcile Job:
   `zuno-admin` (humans, console) and `zuno-automation` (every Job and role, via the Secret `keycloak-automation`). The
   bootstrap `admin` stays only as the first-run fallback and is disabled, not deleted, once the Jobs run as `zuno-automation`.
6. **Seeding is unchanged.** Vault paths are still seeded only when missing (ADR-0345). A new value reaches a seeded cluster
   after its path is deleted and re-seeded; a database also needs the ADR-0529 runbook. Persona families that need a new
   Vault field use a new path (`keycloak/demo-personas-eval`, `-stress`), because an existing path never gets new fields.

## Alternatives considered

- **Keep `secretdemerde` as a literal default in the repository:** simplest for a clone, but publishes the Keycloak admin
  password. Rejected for the admins; the persona literal of ADR-0349 is retired too, so one rule applies.
- **A random fallback at each run:** the Vault seed would fix the first value, but every other reader of the variable
  (derived tokens, checks) would see a different one on each play.
- **A Keycloak client with client credentials for the automation:** no human password, but it does not give the "everything
  on the demo password" the user asked for and changes four consumers instead of one Secret name.
- **Delete the bootstrap `admin` immediately:** no rollback if a consumer was missed. Disabling keeps the way back.

## Consequences

- `ansible/confidential.example.yml` documents both shared variables and the per-component overrides.
- The persona literal of ADR-0349 section 3 is replaced by `zuno_personas_mainpwd`; the live personas keep their Keycloak
  passwords until the Vault path is re-seeded and the persona Job runs.
- Databases pick the new values on a fresh install only; demo333 keeps its current database passwords.
- `platform/vault/tests/test_password_scheme.py` renders the scheme with ansible and fails on a committed literal, an
  unstable fallback, a shared value that does not reach a component, or an override that leaks to another component.
