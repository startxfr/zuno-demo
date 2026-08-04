# postgresql

Installs the CloudNativePG (CNPG) operator via OLM, then applies a
single-instance PostgreSQL `Cluster` (GitOps-managed, see
`gitops/apps/postgresql`) that bootstraps the `zuno` database owned by the
`zuno_app` role. Implements ADR-0015 ("Use PostgreSQL and pgvector as the
persistent data platform").

- `precheck.yml` — verifies the CloudNativePG operator (`cloudnative-pg`
  package) is published in this cluster's OperatorHub catalog, and that
  ArgoCD is already installed (the `Cluster` CR is applied as a GitOps
  Application).
- `prepare.yml` — subscribes to the CloudNativePG operator (OLM
  `Subscription`, `openshift-operators` namespace, mirrors
  `ansible/roles/argocd` and `ansible/roles/external_secrets`) and waits for
  the `clusters.postgresql.cnpg.io` CRD and the operator's controller
  deployment.
- `configure.yml` — applies the `postgresql` GitOps Application
  (`gitops/apps/postgresql/application.yaml`, local chart
  `gitops/charts/postgresql`), which renders:
  - an `ExternalSecret` syncing the pre-seeded `secret/zuno/postgresql/app`
    Vault path (username `zuno_app`, auto-generated password — see
    `ansible/roles/vault/tasks/configure.yml`) into a `zuno-postgresql-app-credentials`
    Kubernetes `Secret` in the `postgresql` namespace;
  - a CNPG `Cluster` (1 instance — demo scope; ADR-0101 tracks HA for v1)
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
tracks — see `gitops/charts/postgresql/image/README.md` for the research
behind this call). Instead, `gitops/charts/postgresql/image/Dockerfile`
layers pgvector onto the stock image via `apt-get install postgresql-16-pgvector`
(the officially documented CNPG custom-image approach). That image must be
built and pushed once by an operator before `make configure postgresql` can
succeed — see the chart's `image/README.md` for the exact command and the
placeholder registry reference used in `values.yaml`. This is the one
manual prerequisite for this role, in the same spirit as the Vault
`google-oauth`/`smtp` placeholder secrets requiring operator input.

## Consumed by

- `ansible/roles/sql_schema` (applies `data/sxa/schema/*.sql` and
  `data/sxa/fixtures/seed.sql` against this cluster).
- `components/mcp-servers/sales-db` (reads the same `zuno_app` credentials
  via its own `ExternalSecret`).
- Track D's RAG service (queries `document_embeddings`, see
  `data/sxa/schema/002_pgvector.sql`).
