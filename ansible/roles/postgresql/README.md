# postgresql

Installs the Crunchy Postgres Operator (PGO) via OLM, then applies a
single-instance PostgreSQL `PostgresCluster` (GitOps-managed, see
`gitops/apps/postgresql`) that bootstraps the `zuno` database owned by the
`zunoapp` role. Implements ADR-0015 ("Use PostgreSQL and pgvector as the
persistent data platform") - that ADR never named a specific operator.

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
mismatches in a row is a pattern, not a fluke: `precheck.yml`/`prepare.yml`
now discover the package by fuzzy name match (`/crunchy/i`) across every
catalog in this cluster's `openshift-marketplace`, not just a hardcoded
package name in a hardcoded catalog, with the same `operatorhubio-catalog`
public fallback CNPG's fix used if nothing crunchy-named is found anywhere.
This is a genuine rewrite either way (CNPG and PGO use different CRDs,
Service names and Secret conventions), not a config tweak.

- `precheck.yml` - verifies *some* crunchy-named package is published
  somewhere in this cluster's catalogs (fuzzy match, not an exact package
  name - see above), and that ArgoCD is already installed (the
  `PostgresCluster` CR is applied as a GitOps Application).
- `prepare.yml` - discovers the actual package name/catalog/channel to
  subscribe from (fuzzy-matches `/crunchy/i` across every PackageManifest
  in `openshift-marketplace`; prefers an exact `crunchy-postgres-operator`
  name and a `stable` channel if present, else whatever fuzzy match/
  `defaultChannel` was found; registers `operatorhubio-catalog` as a
  fallback and retries if nothing matched at all; fails with a clear
  diagnostic - listing every postgres-ish package this cluster's catalogs
  actually publish - rather than guessing a fourth time), subscribes (OLM
  `Subscription`, `openshift-operators` namespace, mirrors
  `ansible/roles/argocd` and `ansible/roles/external_secrets`), and waits
  for the `postgresclusters.postgres-operator.crunchydata.com` CRD. The
  controller Deployment's exact name was **not verified against a live
  cluster** (this environment has no network path to test against - see
  below) - rather than hardcode a guessed name, it's discovered by listing
  every Deployment in `openshift-operators` and matching one whose name
  looks like the PGO controller, polled until OLM actually creates it.
- `configure.yml` - applies the `postgresql` GitOps Application
  (`gitops/apps/postgresql/application.yaml`, local chart
  `gitops/charts/postgresql`), which renders:
  - an `ExternalSecret` syncing the pre-seeded `secret/zuno/postgresql/app`
    Vault path (username `zunoapp`, auto-generated password - see
    `ansible/roles/vault/tasks/configure.yml`) into the
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
image via a PGDG RPM. That image must be built and pushed once by an
operator before `make d0 configure postgresql` can succeed - see
`image/README.md` for the exact commands, the new Crunchy Data registry
signup step (unlike CNPG's public `ghcr.io` image), and three details
flagged there as unverified against a real build (base image tag, package
manager, exact pgvector RPM package name). This is the one manual
prerequisite for this role, in the same spirit as the Vault
`google-oauth`/`smtp` placeholder secrets requiring operator input.

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

- The PGO controller Deployment's exact name/labels (`prepare.yml`
  discovers it rather than hardcoding a guess - see above).
- The exact OLM package name/catalog/channel this cluster actually
  publishes PGO under (`prepare.yml`'s fuzzy `/crunchy/i` discovery - see
  above - handles whatever it turns out to be, but the specific values
  were not confirmed from this environment).
- The `PostgresCluster.status.conditions` `Progressing` condition's exact
  semantics on the installed PGO version (`configure.yml`'s `until`).
- Whether `spec.databaseInitSQL` runs against the `zuno` database as
  intended, or a different default database (see
  `templates/postgrescluster.yaml`'s own comment for the manual fallback
  if not).
- The three pgvector image-build details flagged in `image/README.md`.

Run `make d0 check postgresql` → `make d0 install postgresql` → build/push
the image → `make d0 configure postgresql` against the real cluster and
adjust any of the above that turns out to be wrong.

## Consumed by

- `ansible/roles/sql_schema` (applies `data/sxa/schema/*.sql` and
  `data/sxa/fixtures/seed.sql` against this cluster).
- `components/mcp-servers/sales-db` (reads the same `zunoapp` credentials
  via its own `ExternalSecret`).
- Track D's RAG service (queries `document_embeddings`, see
  `data/sxa/schema/002_pgvector.sql`).
