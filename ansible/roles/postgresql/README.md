# postgresql

Applies the `gitops/apps/postgresql` ArgoCD Application (ADR-0312), whose
chart (`gitops/charts/postgresql`) installs the Crunchy Postgres Operator
(PGO, OLM `Subscription`, sync-wave `"-40"`) and a single-instance
PostgreSQL `PostgresCluster` (sync-wave `"-30"`) that bootstraps the
`zuno` database owned by the `zunoapp` role. Implements ADR-0015 ("Use
PostgreSQL and pgvector as the persistent data platform") - that ADR
never named a specific operator. Previously applied the Subscription
directly via `ansible/tasks/apply_kustomize.yml` (ADR-0310); converted to
this role-applies-one-Application pattern by ADR-0312, alongside
`keycloak` (the other role sharing this "operand's `ExternalSecret`s
depend on `external_secrets` having run first" shape - both sort after
`external_secrets` in `day0_components`).

## Why PGO, not CloudNativePG

This role originally used CloudNativePG (CNPG). It was switched to PGO
after two rounds of real friction on an actual cluster: CNPG's
`cloudnative-pg` package wasn't published by any enabled catalog there
(needing a manual `operatorhubio-catalog` fallback to fix), and once
found, the catalog's channel name (`stable-v1`) didn't match what this
role had hardcoded (`stable`).

PGO was first wired up assuming its OLM package
(`crunchy-postgres-operator`) would reliably be published from
`redhat-operators`, one of OpenShift's four *default* CatalogSources, with
no fallback/discovery workaround needed - **also proven wrong** on a real
cluster (OLM's `Subscription.status` reported `ResolutionFailed`: "no
operators found in package crunchy-postgres-operator in the catalog
referenced by subscription"). Three real-world catalog/channel/package-name
mismatches in a row is a pattern, not a fluke: `install.yml` discovers
the package by fuzzy name match (`/crunchy/i`) across every catalog in
this cluster's `openshift-marketplace`, not just a hardcoded package name
in a hardcoded catalog, with the same `operatorhubio-catalog` public
fallback CNPG's fix used if nothing crunchy-named is found anywhere. This
is a genuine rewrite either way (CNPG and PGO use different CRDs, Service
names and Secret conventions), not a config tweak.

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
  `gitops_app_extra_helm_values` (ADR-0048) on the `-d0` call. The chart
  renders, split across the two Applications (`operator.enabled` for `-d0`,
  `postgresCluster.enabled` for `-d1` - ADR-0312's addendum):
  - the OLM `Subscription` itself (`-d0`, `openshift-operators`
    namespace - mirrors `ansible/roles/argocd` and
    `ansible/roles/external_secrets`; no `OperatorGroup` needed, that
    namespace ships with OpenShift's own default global one) - gated
    ahead of `-d1` (applied only once `-d0` is Synced+Healthy) by the
    custom health check
    `ansible/roles/argocd/tasks/apply_resource_health_checks.yml`
    registers (ADR-0312);
  - an `ExternalSecret` syncing the pre-seeded `zuno/postgresql/app`
    Vault path (username `zunoapp`, auto-generated password - see
    `ansible/roles/vault/tasks/install.yml`) into the
    `zuno-postgresql-pguser-zunoapp` Kubernetes `Secret` - PGO's own
    fixed naming convention (`<cluster>-pguser-<user>`), pre-created with
    PGO's two required labels so PGO's "bring your own password"
    mechanism (>= 5.6) adopts this password instead of generating its own
    (the Postgres role is named `zunoapp`, not the CNPG-era `zuno_app` -
    `helm lint` caught that PGO's `<cluster>-pguser-<user>` Secret name
    must be a valid Kubernetes RFC 1123 label, which rules out
    underscores, and unquoted PostgreSQL identifiers can't contain
    hyphens either, so a name valid in both had to drop the separator
    entirely);
  - a `PostgresCluster` (1 instance - demo scope; ADR-0101 tracks HA for
    v1) with 5Gi storage, one local PVC-backed pgBackRest repo (PGO
    requires at least one - there's no way to omit backups entirely,
    unlike CNPG), creating the `zuno` database owned by `zunoapp`, and
    running `CREATE EXTENSION IF NOT EXISTS vector;` via
    `spec.databaseInitSQL` referencing a `ConfigMap`.

Then waits for the `PostgresCluster`'s `Progressing` condition to report
`False` (PGO's documented rollout-complete signal - not CNPG's single
`status.phase` string).

## pgvector

PGO does not bundle pgvector out of the box either (open, unresolved
upstream issue `CrunchyData/postgres-operator#3706`) - same situation
this demo already had with CloudNativePG. `gitops/charts/postgresql/
image/Dockerfile` layers pgvector onto Crunchy's own UBI-based operand
image via a PGDG RPM. `install.yml` now builds and imports this image
itself, on-cluster, the same `zuno-ai-build` BuildConfig/ImageStream
mechanism every other component's image uses
(`ansible/tasks/apply_openshift_build.yml`, ADR-0056) - the one
difference being the Dockerfile's `FROM` pulls from
`registry.developers.crunchydata.com`, which needs a free Crunchy Data
developer account even just to pull, so this build also needs
`zuno_crunchydata_registry_username`/`_password` in
`ansible/confidential.yml` (same operator-supplied-credential pattern as
the Vault `google-oauth`/`smtp`/`confluence` fields). Without those two
fields set, `install.yml` skips the build with a clear warning and the
`PostgresCluster` sits `ImagePullBackOff` until they're added and `make
d0 install postgresql` is re-run - see `image/README.md` for the account
signup step and three details flagged there as unverified against a real
build (base image tag, package manager, exact pgvector RPM package name).

## Connecting to this cluster

PGO auto-creates several Services for a `PostgresCluster` named
`zuno-postgresql`: `zuno-postgresql-primary` (the one every consumer
below uses), `-replicas`, `-pods`, `-ha`, `-ha-config`. Every consumer
connects to `zuno-postgresql-primary.zuno-data.svc.cluster.local:5432`.
There is no plain `postgresql` Service, and no `-rw`-suffixed Service
either (that was CNPG's convention, not PGO's) - nothing in this
repository creates one.

## What's unverified against a real cluster

This environment has no network path to the real OpenShift cluster this
role targets (confirmed by a direct connection timeout while
investigating the original CNPG catalog issue), so the following were
researched from Crunchy's own documentation but not exercised end to end:

- The exact OLM package name/catalog/channel this cluster actually
  publishes PGO under (`install.yml`'s fuzzy `/crunchy/i` discovery - see
  above - handles whatever it turns out to be, but the specific values
  were not confirmed from this environment).
- The `PostgresCluster.status.conditions` `Progressing` condition's exact
  semantics on the installed PGO version (`install.yml`'s `until`).
- Whether `spec.databaseInitSQL` runs against the `zuno` database as
  intended, or a different default database (see
  `templates/postgrescluster.yaml`'s own comment for the manual fallback
  if not).
- The three pgvector image-build details flagged in `image/README.md`.
- The `strategy.dockerStrategy.pullSecret` mechanism `ansible/tasks/
  apply_openshift_build.yml` relies on to authenticate the Crunchy Data
  base-image pull - not exercised against a real `BuildConfig` from this
  environment.

Run `make d0 check postgresql` → fill in `ansible/confidential.yml`'s
Crunchy Data credentials → `make d0 install postgresql` against the real
cluster and adjust any of the above that turns out to be wrong.

## Consumed by

- `ansible/roles/sql_schema` (applies `data/sxa/schema/*.sql` and
  `data/sxa/fixtures/seed.sql` against this cluster).
- `components/mcp-servers/sales-db` (reads the same `zunoapp` credentials
  via its own `ExternalSecret`).
- Track D's RAG service (queries `document_embeddings`, see
  `data/sxa/schema/002_pgvector.sql`).
