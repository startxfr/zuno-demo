# postgresql

Installs the CloudNativePG (CNPG) operator via OLM, then applies a
single-instance PostgreSQL `Cluster` (GitOps-managed, see
`gitops/apps/postgresql`) that bootstraps the `zuno` database owned by the
`zuno_app` role. Implements ADR-0015 ("Use PostgreSQL and pgvector as the
persistent data platform").

- `precheck.yml` - verifies the CloudNativePG operator (`cloudnative-pg`
  package) is published in this cluster's OperatorHub catalog, and that
  ArgoCD is already installed (the `Cluster` CR is applied as a GitOps
  Application). Fails if `cloudnative-pg` isn't found anywhere yet -
  `precheck` stays read-only and never registers a `CatalogSource` itself
  (see below), so it correctly reports this as a hard stop even though
  `prepare` may be able to resolve it automatically.
- `prepare.yml` - **discovers** which enabled catalog actually publishes
  `cloudnative-pg` (ADR-0048-style: never hardcodes `certified-operators`,
  since EDB's certified build isn't mirrored into every cluster's
  certified-operators snapshot). If no enabled catalog on this cluster
  carries it at all, registers the well-known public
  `operatorhubio-catalog` `CatalogSource`
  (`quay.io/operatorhubio/catalog:latest`, the canonical community catalog
  that carries CloudNativePG on plain OLM) as a fallback, waits for it to
  report `READY`, and re-discovers. Fails with a clear diagnostic if
  `cloudnative-pg` is still not found after that (check outbound access to
  `quay.io` and any NetworkPolicy/proxy in front of it) - never silently
  gives up or substitutes a different operator. **Channel** is discovered
  the same way, not hardcoded either: prefers an exact `stable-v1` match
  (confirmed against a real cluster - some catalogs publish CloudNativePG
  under a bare `stable` channel, others under `stable-v1`, and a
  Subscription naming a channel the catalog doesn't actually have fails
  with an OLM "wrong channel" error), then any `stable*`-prefixed channel,
  then the manifest's own `defaultChannel`, failing loudly (listing every
  published channel) if none of those exist. Then subscribes to whichever
  catalog/channel combination actually won (OLM `Subscription`,
  `openshift-operators` namespace, mirrors `ansible/roles/argocd` and
  `ansible/roles/external_secrets`, `installPlanApproval: Automatic` -
  tracks the channel's latest CSV rather than pinning an exact version;
  add `startingCSV` + switch to `Manual` approval if you need to pin one
  specific CSV instead) and waits for the `clusters.postgresql.cnpg.io`
  CRD and the operator's controller deployment, then reports the
  `Subscription.status.installedCSV` it actually resolved to.
- `configure.yml` - applies the `postgresql` GitOps Application
  (`gitops/apps/postgresql/application.yaml`, local chart
  `gitops/charts/postgresql`), which renders:
  - an `ExternalSecret` syncing the pre-seeded `secret/zuno/postgresql/app`
    Vault path (username `zuno_app`, auto-generated password - see
    `ansible/roles/vault/tasks/configure.yml`) into a `zuno-postgresql-app-credentials`
    Kubernetes `Secret` in the `zuno-data` namespace;
  - a CNPG `Cluster` (1 instance - demo scope; ADR-0101 tracks HA for v1)
    with 5Gi storage, bootstrapping the `zuno` database owned by `zuno_app`
    using that Secret, and running `CREATE EXTENSION IF NOT EXISTS vector;`
    as part of `bootstrap.initdb.postInitSQL`.

Then waits for the `Cluster` to report `status.phase: Cluster in healthy
state`.

## pgvector

The stock CloudNativePG operand image
(`ghcr.io/cloudnative-pg/postgresql:16-bookworm`) does **not** bundle
pgvector. This demo does not rely on CNPG's newer "ImageVolume extensions"
mechanism (CNPG >= 1.27, requires the Kubernetes `ImageVolume` feature gate,
which is beta-and-off-by-default at the Kubernetes versions OpenShift 4.20
tracks - see `gitops/charts/postgresql/image/README.md` for the research
behind this call). Instead, `gitops/charts/postgresql/image/Dockerfile`
layers pgvector onto the stock image via `apt-get install postgresql-16-pgvector`
(the officially documented CNPG custom-image approach). That image must be
built and pushed once by an operator before `make configure postgresql` can
succeed - see the chart's `image/README.md` for the exact command and the
placeholder registry reference used in `values.yaml`. This is the one
manual prerequisite for this role, in the same spirit as the Vault
`google-oauth`/`smtp` placeholder secrets requiring operator input.

## Connecting to this cluster

CNPG auto-creates three Services for a `Cluster` named `zuno-postgresql`:
`zuno-postgresql-rw` (primary, read-write, the one every consumer below
uses), `zuno-postgresql-ro` and `zuno-postgresql-r` (replicas - unused in
this demo's single-instance scope). Every consumer connects to
`zuno-postgresql-rw.zuno-data.svc.cluster.local:5432` - CNPG's own
managed, failover-aware read-write endpoint. There is no plain
`postgresql` Service; nothing in this repository creates one.

## Consumed by

- `ansible/roles/sql_schema` (applies `data/sxa/schema/*.sql` and
  `data/sxa/fixtures/seed.sql` against this cluster).
- `components/mcp-servers/sales-db` (reads the same `zuno_app` credentials
  via its own `ExternalSecret`).
- Track D's RAG service (queries `document_embeddings`, see
  `data/sxa/schema/002_pgvector.sql`).
