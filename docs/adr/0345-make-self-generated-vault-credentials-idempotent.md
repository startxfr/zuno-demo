# ADR-0345: Make self-generated Vault credentials idempotent across ansible re-runs

- **Status:** Implemented
- **Target:** v0.1
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team

## Context

`maas-api` went CrashLoopBackOff live (2026-08-13, shortly after ADR-0343 landed) with `failed SASL auth: FATAL: password authentication failed for user "maas"`. Investigation found two stacked bugs, not one:

1. **Password rotation on every ansible re-run.** `ansible/roles/vault/tasks/install.yml` seeds ~13 self-generated credentials (five app credentials in the `_vault_generated_secrets` dict, plus MariaDB's root password, the rag-ingestion pipeline DB password, Redis, MCP, and two Tekos/Keycloak OIDC client secrets) using `lookup('ansible.builtin.password', '/dev/null', ...)`. Per `ansible-doc password`: *"A special case is using /dev/null as a path. The password lookup will generate a new random password each time, but will not write it to /dev/null."* Every task then ran an unconditional `vault kv put`, overwriting Vault on every single run of the vault role - confirmed live: `zuno-postgresql-pguser-maas`, `-keycloak`, `-ragtech`, `-zunoapp`, and both MariaDB ExternalSecrets all showed `Updated Secret` events within the same few-minute window after an unrelated `make d0 install vault` re-run. `mariadb-0` self-healed once the MariaDB operator reconciled its rotated root password; `maas-api` didn't, because its `maas-db-config` copy (a *second*, independent ExternalSecret reading the same Vault path into a different namespace) has a 1h `refreshInterval` and hadn't caught up yet.
2. **A separate, masked bug**: once the password mismatch was manually resolved (force-refreshing `maas-db-config`), `maas-api` still failed with `permission denied for schema public`. `gitops/charts/postgresql/templates/configmap-init-sql.yaml`'s `databaseInitSQL` - which PGO runs exactly once, at cluster bootstrap - only grants `SCHEMA public` privileges to `cluster.owner` (zunoapp) and `keycloakDatabase.owner` (keycloak). `ragTechDatabase` and `maasDatabase` were added to `spec.users` later (ADR-0330, ADR-0343) and never got an equivalent grant, since bootstrap-time SQL doesn't re-run for users added afterward. Since PG15 the `public` schema is owned by `pg_database_owner`, not granted to `PUBLIC`, so both `maas` and (latently, unexercised until now) `ragtech` could connect but not `CREATE TABLE`.

## Decision

- **Idempotent Vault seeding**: new shared task `ansible/tasks/vault_seed_if_missing.yml` - checks `vault kv get zuno/<path>` first and only runs `vault kv put` when that path doesn't exist yet, mirroring the check-then-write pattern the same file already uses for operator-supplied secrets (`google-oauth/client` etc.) further down. All ~13 self-generated `vault kv put` tasks in `ansible/roles/vault/tasks/install.yml` now call this shared task instead of writing unconditionally; the password-generation expressions themselves (and any `zuno_admin_*_password` override from `confidential.yml`) are unchanged, only the write is now guarded.
- **Bootstrap-SQL grant, corrected for future installs**: `configmap-init-sql.yaml` now also grants `SCHEMA public` to `ragTechDatabase.owner` and `maasDatabase.owner`. This only affects future/greenfield cluster bootstraps - `databaseInitSQL` does not retroactively run for already-provisioned clusters.
- **Live remediation** (this cluster, one-time): the stale `maas-db-config` Secret was deleted so ESO recreated it immediately from Vault's current (correct) password; `GRANT ALL ON SCHEMA public TO maas;` still needs to be run once by hand against the live `maas` database (not executed as part of this change - flagged for the operator, since it's a direct, unreviewed write against a shared PostgreSQL cluster).

## Consequences

Re-running any `make d0 install vault` (or a full `make d0 install`) no longer rotates already-seeded credentials, so downstream consumers (PGO pguser secrets, MariaDB, Redis, Keycloak/Tekos OIDC clients) stop desyncing from each other on unrelated re-runs. Rotating a credential deliberately now requires removing it from Vault first (`vault kv delete`/`vault kv destroy`) or setting the matching `zuno_admin_*` override and clearing the old value - it's no longer implicit on every run. Adding a new dedicated database to the shared PostgreSQL cluster (beyond `zunoapp`/`keycloak`/`ragtech`/`maas`) still requires both a `configmap-init-sql.yaml` entry *and*, for already-running clusters, a one-time manual `GRANT ALL ON SCHEMA public` - `databaseInitSQL` only fires at first bootstrap.

## Security considerations

No credential material changes shape or storage location - still Vault-only, `no_log: true` throughout. The idempotency check itself (`vault kv get`) is read-only and already covered by the same Vault policy the seeding tasks use.

## Operational considerations

`rag-tech`'s database has the same latent missing-grant gap as `maas` did (confirmed live: its `public` schema also lacks a `ragtech` grant) but is not yet failing because nothing in the rag-ingestion pipeline has attempted a `CREATE TABLE` in `public` there yet. Not fixed here - flagged for a follow-up GRANT before that surfaces as a live incident.

## Acceptance criteria

- Running `make d0 install vault` (or the underlying playbook) twice in a row produces no `vault kv put`/`Updated Secret` events on the second run for any of the ~13 self-generated paths.
- `maas-api` runs 2/2 with no SASL auth errors and no `permission denied for schema public` errors in its logs.
- Any future dedicated PostgreSQL database added to `gitops/charts/postgresql` includes a matching `GRANT ALL ON SCHEMA public` entry in `configmap-init-sql.yaml`, and its rollout runbook notes the one-time manual grant needed on already-running clusters.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0315](0315-dedicated-keycloak-postgresql-database.md)
- [ADR-0330](0330-integrate-the-rag-ingestion-pipeline-as-a-day1-component.md)
- [ADR-0343](0343-complete-the-maas-and-ray-prerequisites-on-the-datasciencecluster.md)
