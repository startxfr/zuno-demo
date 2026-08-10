# ADR-0315: Dedicated Keycloak database/role on the shared PostgreSQL cluster

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-10
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0015 established PostgreSQL/pgvector (`ansible/roles/postgresql`,
`gitops/charts/postgresql`) as the shared persistent data platform, without
naming a specific operator; ADR-0312 subsequently converted it (and
`keycloak`) into a `-d0`/`-d1` operator/operand Application pair. Every
existing consumer of that cluster - `sql_schema`, `rag`,
`components/mcp-servers/sales-db` - shares one database/role,
`zuno`/`zunoapp`, provisioned via PGO's `spec.users[]` on the
`PostgresCluster`.

`ansible/roles/keycloak` needs its own database. PGO's `spec.users[].
databases` model grants a role full, unscoped rights over the databases it
lists - there is no per-schema or per-table restriction available at that
layer. Keycloak owns and migrates its own schema on every version upgrade
(via Liquibase, driven by the operator/Keycloak itself, not this repo).
Sharing the `zunoapp`/`zuno` pair would give Keycloak blanket rights over
every other consumer's tables and vice versa - a real regression against
this repo's least-privilege/Vault-only credential conventions (ADR-0024),
not a theoretical one, since `zunoapp` already backs `sql_schema`'s and
`rag`'s application data.

Wiring credentials to a second database/role hits the same obstacle
`components/mcp-servers/sales-db` already solved: the PGO-managed
`pguser` Secret it creates lives in `zuno-data` (where the
`PostgresCluster` lives), but Keycloak's pod lives in `zuno-auth`, and a
`Deployment`/CR's `secretKeyRef` cannot reference a Secret in a different
namespace.

## Decision

Add a second `spec.users[]` entry to the `PostgresCluster`
(`gitops/charts/postgresql/templates/postgrescluster.yaml`), driven by
`keycloakDatabase.owner`/`.name` (`gitops/charts/postgresql/values.yaml`:
`keycloak`/`keycloak`), alongside the existing `cluster.owner`/`.database`
(`zunoapp`/`zuno`) entry. `spec.users[]` becomes a two-entry list; each
entry keeps its own PGO-managed `<cluster>-pguser-<user>` Secret
(`zuno-postgresql-pguser-keycloak`) in `zuno-data`.

Credentials are seeded once in Vault and consumed independently on both
sides of the namespace boundary, mirroring the `mcp-sales-db` "own
ExternalSecret + secretKeyRef" pattern:

- `ansible/roles/vault/tasks/install.yml` seeds `zuno/keycloak/postgresql-app`
  (username `keycloak`, auto-generated password) alongside the other
  `keycloak/*` Vault entries.
- `gitops/charts/postgresql/templates/externalsecret-keycloak.yaml` syncs
  that same Vault path into the PGO-conventional
  `zuno-postgresql-pguser-keycloak` Secret in `zuno-data`, so PGO's "bring
  your own password" mechanism (>= 5.6) adopts it instead of generating its
  own.
- `gitops/charts/keycloak/templates/externalsecret-postgresql.yaml`
  independently resolves the identical Vault path into
  `keycloak-postgresql-app` in `zuno-auth`, which the `Keycloak` CR's
  `spec.db.usernameSecret`/`passwordSecret` reference directly.

Keycloak connects to `zuno-postgresql-primary.zuno-data.svc.cluster.local`
directly rather than through `zuno-postgresql-pgbouncer` like every other
consumer - a separate, narrower exception (PgBouncer's `poolMode:
transaction` doesn't reliably support the server-side prepared statements
Keycloak's JDBC layer relies on under sustained load), applied here rather
than left as an unverified live risk.

No new cross-role ordering/health-check gating was needed: `postgresql`
already precedes `keycloak` in `day0_components`
(`ansible/playbooks/day0_install.yml`), and `postgresql`'s `install.yml`
already blocks until the `PostgresCluster` (and therefore the new
`keycloak` database/role) is ready before returning.

## Alternatives considered

- **Share the existing `zunoapp`/`zuno` database/role.** Rejected: PGO
  grants no per-schema scoping, so this would give Keycloak and every other
  consumer blanket rights over each other's tables - unacceptable given
  this repo's least-privilege conventions, and Keycloak's own
  schema-migration lifecycle is independent of `sql_schema`'s/`rag`'s.
- **Stand up a second, dedicated `PostgresCluster` for Keycloak.** Rejected
  as unnecessary operational overhead (a second HA Patroni cluster, second
  PgBouncer, second backup repo) for one small, low-throughput database;
  PGO's multi-database-per-cluster support already provides adequate
  isolation at the role/database level for this demo's scope.

## Consequences

`gitops/charts/postgresql/templates/postgrescluster.yaml`'s `spec.users[]`
is a two-entry list. A new `ExternalSecret`
(`gitops/charts/postgresql/templates/externalsecret-keycloak.yaml`) and
`keycloakDatabase` values block exist alongside the pre-existing
`cluster`/`credentials` ones. `gitops/charts/namespaces` grants `zuno-auth`
in `zuno-data`'s `allowedFromNamespaces`, since that namespace's
NetworkPolicy default-denies ingress otherwise.

See [Standard clauses](README.md#standard-clauses) for Migration/evolution.

## Security considerations

No privilege escalation: the `keycloak` role is granted rights only over
its own `keycloak` database, not `zuno`. Credentials are Vault-generated
and never hardcoded in Git (ADR-0024), consistent with every other
consumer of this cluster.

## Related ADRs

- [ADR-0015](0015-use-postgresql-and-pgvector-as-the-persistent-data-platform.md) (the platform choice this ADR builds on)
- [ADR-0312](0312-route-operator-installs-through-argocd-applications.md) (the `-d0`/`-d1` Application pattern both `postgresql` and `keycloak` follow)
- [ADR-0024](0024-use-vault-for-application-secrets.md) (the never-hardcode-credentials convention this ADR upholds)

## Review evidence

Grounded in a direct read of `gitops/charts/postgresql/values.yaml` and
`templates/postgrescluster.yaml` (`spec.users[]`'s two entries),
`gitops/charts/postgresql/templates/externalsecret-keycloak.yaml`,
`gitops/charts/keycloak/values.yaml` and `templates/externalsecret-
postgresql.yaml`, `gitops/charts/namespaces/values.yaml`'s
`allowedFromNamespaces`, `ansible/roles/vault/tasks/install.yml`'s
`zuno/keycloak/postgresql-app` seed, and the "Database" sections of
`ansible/roles/keycloak/README.md` and `ansible/roles/postgresql/README.md`
(both already narrated this decision before this ADR document existed).
