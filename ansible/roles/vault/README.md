# vault

Installs Vault (via the `vault` GitOps Application, demo-grade single
replica with file storage), initializes and unseals it, then configures the
Kubernetes auth method and the `eso-reader` policy/role that
`ansible/roles/external_secrets` binds its `ClusterSecretStore` to, plus
the `pki/` secrets engine (a self-signed root CA, `common_name:
zuno-demo.internal`) and the `cert-manager-issuer` policy/role that
`ansible/roles/cert_manager` binds its `ClusterIssuer` to. Both are
prepared by the same idempotent script,
`ansible/roles/vault/kustomize/unseal-configure/configmap.yaml`, and each
consumer only ever *references* them declaratively.

`pki/roles/cert-manager`'s `allowed_domains` also includes the cluster's
real apps wildcard domain (`${CLUSTER_BASE_DOMAIN}`, resolved early via
`ansible/tasks/resolve_cluster_base_domain.yml` and injected into the
unseal-configure Job's env), not just `zuno-demo.internal`/
`svc.cluster.local` - `ansible/roles/keycloak`'s Ingress requests a
cert-manager cert for a public-facing hostname (`keycloak.<domain>`),
which Vault's PKI role would otherwise reject as out of domain.

This is the one role that cannot depend on Vault for its own bootstrap
secret: `install.yml` captures the unseal key and root token into a
Kubernetes `Secret` (`vault-bootstrap-credentials`) in a locked-down,
admin-only namespace (`zuno-vault`) rather than requiring any
external input.

`install.yml` also generates and seeds the secrets that can be
self-generated (Keycloak admin, PostgreSQL app credentials, MariaDB root,
and the rag-ingestion pipeline's internal `mlpipeline` metadata-DB
password). The rest require external input: the Google Workspace OAuth
client, the SMTP technical-mail credentials, the Atlassian Confluence
technical token, the Quay registry credentials (stored for future
cluster-side use - separate from the GitHub Actions
`QUAY_USERNAME`/`QUAY_PASSWORD` CI secrets), the Atlassian Jira technical
token (unused, reserved ahead of time), and the RAG corpus S3 bucket
credentials. Those come from `ansible/confidential.yml` -
copied from the checked-in `ansible/confidential.example.yml` and filled
in by an operator before the first `make d0 install vault`, gitignored so
no secret is ever written to a Git-tracked file. `install.yml` re-reads it
on every run and (re-)seeds Vault from it, so the file can be deleted
again afterwards unless Vault needs to be reinstalled. Any field left as
the example file's `"xxxxxx"` sentinel falls back to an empty Vault
placeholder (Google OAuth, SMTP, Confluence, Quay, Jira) or is simply not
seeded at all (RAG S3 and the PostgreSQL/MariaDB backup S3 credentials) -
never overwriting a real value however it got there.

Vault's KV v2 secrets engine is mounted at `zuno/` (not the HashiCorp
default `secret/`) - every platform secret lives under `zuno/<component>/
<item>`, matching the `eso-reader` policy scope below.
