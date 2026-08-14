# postgresql

Applies the `gitops/apps/postgresql` ArgoCD Application, whose
chart (`gitops/charts/postgresql`) installs the Crunchy Postgres Operator
(PGO, OLM `Subscription`, sync-wave `"-40"`) and a 3-instance, PgBouncer-
fronted PostgreSQL `PostgresCluster` (sync-wave `"-30"`) that bootstraps
the `zuno` database owned by the `zunoapp` role. Implements ADR-0015 ("Use
PostgreSQL and pgvector as the persistent data platform") - that ADR
never named a specific operator.

## Why PGO, not CloudNativePG

This role originally used CloudNativePG (CNPG), switched to PGO after
catalog/channel mismatches on a real cluster: CNPG's `cloudnative-pg`
package wasn't published by any enabled catalog there (needing a manual
`operatorhubio-catalog` fallback), and once found, the catalog's channel
name (`stable-v1`) didn't match what this role had hardcoded (`stable`).
PGO's own OLM package (`crunchy-postgres-operator`) also isn't reliably
published from `redhat-operators` on every cluster (`Subscription.status`
can report `ResolutionFailed`: "no operators found in package
crunchy-postgres-operator in the catalog referenced by subscription").
`install.yml` therefore discovers the package by fuzzy name match
(`/crunchy/i`) across every catalog in this cluster's
`openshift-marketplace`, not a hardcoded package name in a hardcoded
catalog, with the same `operatorhubio-catalog` public fallback if
nothing crunchy-named is found anywhere.

- `precheck.yml` - state detection, never fails: reports whether the
  `zuno-postgresql-d0`/`zuno-postgresql-d1` Applications/`PostgresCluster`
  are actually Synced+Healthy/rolled out, setting `postgresql_state_installed`
  and a line in the shared `/tmp` state report (see
  `ansible/playbooks/day0_check.yml`).
- `install.yml` - fuzzy-matches `/crunchy/i` across every PackageManifest
  in `openshift-marketplace`, registering `operatorhubio-catalog` as a
  fallback and retrying if nothing matched at all, failing with a clear
  diagnostic - listing every postgres-ish package this cluster's catalogs
  actually publish - rather than guessing a fourth time. Then selects the
  exact package name/catalog/channel (prefers an exact
  `crunchy-postgres-operator` name and a `stable` channel if present,
  else whatever fuzzy match/`defaultChannel` was found) and applies the
  `postgresql` GitOps Applications (`gitops/apps/postgresql/application-d0.yaml`
  then `application-d1.yaml`, both against local chart
  `gitops/charts/postgresql`) with that selection passed via
  `gitops_app_extra_helm_values` on the `-d0` call. The chart renders,
  split across the two Applications (`operator.enabled` for `-d0`,
  `postgresCluster.enabled` for `-d1`):
  - the OLM `Subscription` itself (`-d0`, `openshift-operators`
    namespace - mirrors `ansible/roles/argocd` and
    `ansible/roles/external_secrets`; no `OperatorGroup` needed, that
    namespace ships with OpenShift's own default global one) - gated
    ahead of `-d1` (applied only once `-d0` is Synced+Healthy) by the
    custom health check
    `ansible/roles/argocd/tasks/apply_resource_health_checks.yml`
    registers;
  - an `ExternalSecret` syncing the pre-seeded `zuno/postgresql/app`
    Vault path (username `zunoapp`, auto-generated password - see
    `ansible/roles/vault/tasks/install.yml`) into the
    `zuno-postgresql-pguser-zunoapp` Kubernetes `Secret` - PGO's own
    fixed naming convention (`<cluster>-pguser-<user>`), pre-created with
    PGO's two required labels so PGO's "bring your own password"
    mechanism (>= 5.6) adopts this password instead of generating its own
    (the Postgres role is named `zunoapp`, not the CNPG-era `zuno_app`:
    PGO's `<cluster>-pguser-<user>` Secret name must be a valid
    Kubernetes RFC 1123 label, which rules out underscores, and unquoted
    PostgreSQL identifiers can't contain hyphens either, so a name valid
    in both had to drop the separator entirely);
  - a `PostgresCluster` (3 Patroni instances for HA, PgBouncer x2 in
    front, separate data/WAL volumes, one local PVC-backed pgBackRest
    repo always plus a second S3-compatible one once real credentials
    exist - PGO requires at least one repo, there's no way to omit
    backups entirely unlike CNPG), creating the `zuno` database owned by
    `zunoapp`, and running `CREATE EXTENSION IF NOT EXISTS vector;`/
    `CREATE EXTENSION IF NOT EXISTS timescaledb;` via
    `spec.databaseInitSQL` referencing a `ConfigMap`.

Then waits for `status.instances[].readyReplicas` to match `.replicas`
(summed across every instance set) plus the `ProxyAvailable` condition -
PGO 5.8.8 does not set a `Progressing` condition once a cluster is
stable (`kubectl wait --for=condition=Progressing=False` never matches
on this version).

## pgvector and TimescaleDB

No custom image or on-cluster build - PGO 5.8.8's own default operand
image for `postgresVersion: 18` already bundles pgvector 0.8.2 and
TimescaleDB 2.27.1: `SELECT extname, extversion FROM pg_extension;`
reports both once created. `templates/postgrescluster.yaml` omits
`spec.image` entirely so PGO resolves its own certified image, already
reachable through the cluster's existing global pull secret - no
separate registry account needed. TimescaleDB additionally needs
`shared_preload_libraries=timescaledb` (`spec.config.parameters`,
confirmed via `SHOW shared_preload_libraries;`); both extensions are
created via `CREATE EXTENSION IF NOT EXISTS ...` in `spec.databaseInitSQL`'s
`ConfigMap` (pgvector needs no preload entry) - that script must
`\connect` to the app database first, PGO runs it against `postgres`
otherwise (see that file's own comment).

## Connecting to this cluster

PGO auto-creates several Services for a `PostgresCluster` named
`zuno-postgresql`: `zuno-postgresql-primary` (direct, bypasses pooling),
`-replicas`, `-pods`, `-ha`, `-ha-config`, and - since `spec.proxy.
pgBouncer` is configured - `zuno-postgresql-pgbouncer`. **Every consumer
connects through PgBouncer**, `zuno-postgresql-pgbouncer.zuno-data.svc.
cluster.local:5432` (transaction pooling), not `-primary` directly -
except `ansible/roles/keycloak`, which connects to
`zuno-postgresql-primary` directly, since Keycloak's JDBC layer relies on
server-side prepared statements that transaction-mode pooling doesn't
reliably support under sustained load. There is no plain `postgresql`
Service, and no `-rw`-suffixed Service either (that was CNPG's convention,
not PGO's) - nothing in this repository creates one.

## What's unverified against a real cluster

This environment has no network path to the real OpenShift cluster this
role targets, so the following were researched from Crunchy's own
documentation but not exercised end to end:

- The exact OLM package name/catalog/channel this cluster actually
  publishes PGO under (`install.yml`'s fuzzy `/crunchy/i` discovery -
  see above - handles whatever it turns out to be, but the specific
  values were not confirmed from this environment).
- Whether PGO 5.8.8's default operand image for `postgresVersion: 18`
  really does bundle pgvector 0.8.2 and TimescaleDB 2.27.1 as expected -
  see "pgvector and TimescaleDB" above.
- `cluster.storageClassName` (`gitops/charts/postgresql/values.yaml`) -
  AWS/EBS-backed, `gp3-csi` (cluster default). Re-check with
  `oc get storageclass` on any other target cluster.
- The `spec.backups.pgbackrest.repos[].s3`/`.configuration` shape in
  `templates/postgrescluster.yaml` and the `s3.conf` file format in
  `templates/externalsecret-backup-s3.yaml` - reconstructed from
  Crunchy's general pgBackRest S3 documentation, not confirmed against
  the installed CRD (`oc explain postgrescluster.spec.backups.pgbackrest
  --recursive`).
- `spec.proxy.pgBouncer` and `spec.openshift`/`spec.config.parameters`
  field names/shapes - not exercised against a real `PostgresCluster`
  from this environment.

Run `make d0 check postgresql` → `make d0 install postgresql` against
the real cluster and adjust any of the above that turns out to be wrong.

## Consumed by

- `ansible/roles/sql_schema` (applies `data/sxa/schema/*.sql` and
  `data/sxa/fixtures/seed.sql` against this cluster) and `ansible/roles/
  rag` (applies the RAG schema/fixtures the same way) - both one-shot
  Jobs, connecting through PgBouncer.
- `components/mcp-servers/sales-db` (reads the same `zunoapp` credentials
  via its own `ExternalSecret`).
- Track D's RAG service (queries `document_embeddings`, see
  `data/sxa/schema/002_pgvector.sql`).
- `ansible/roles/keycloak` - a **second**, dedicated `keycloak`/`keycloak`
  database/role (not `zunoapp`/`zuno`), via its own `ExternalSecret`
  (`gitops/charts/keycloak/templates/externalsecret-postgresql.yaml`)
  reading the same `zuno/keycloak/postgresql-app` Vault path this
  chart's `templates/externalsecret-keycloak.yaml` also resolves - same
  cross-namespace pattern as `mcp-sales-db`.
- `ansible/roles/rag_ingestion` - a **third**, dedicated `ragtech`/
  `rag-tech` database/role for the ingestion pipeline's structured
  corpus/index tables, via its own `ExternalSecret`
  (`gitops/charts/rag-ingestion/templates/external-secrets.yaml`) reading
  the same `zuno/rag/postgresql-app` Vault path this chart's
  `templates/externalsecret-ragtech.yaml` also resolves - same
  cross-namespace pattern as Keycloak above. `spec.users[]` in
  `templates/postgrescluster.yaml` is accordingly a three-entry list now.
