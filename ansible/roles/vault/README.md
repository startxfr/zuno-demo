# vault

Installs Vault (via the `vault` GitOps Application: raft storage, one
replica ready to grow to three, AWS KMS auto-unseal, listener TLS from the
OpenShift service CA - ADR-0602 clause 1 / WP-223), initializes it on the
first run, then configures the Kubernetes auth method, the per-namespace
External Secrets roles (`ns-<namespace>`, from
`platform/vault/secret-access.yaml`), the `pki/` secrets engine (a
self-signed root CA, `common_name: zuno-demo.internal`) and the
`cert-manager-issuer`/`istio-issuer`/`mariadb-issuer` policies and roles
the ClusterIssuers bind to, plus Transit and the audit device. All of it is
prepared by one idempotent script, `kustomize/configure/configure.sh`, run
by the `vault-configure` Job (`tasks/run_configure_job.yml`); each consumer
only ever *references* it declaratively.

`pki/roles/cert-manager`'s `allowed_domains` also includes the cluster's
real apps wildcard domain (`${CLUSTER_BASE_DOMAIN}`, resolved early via
`ansible/tasks/resolve_cluster_base_domain.yml` and injected into the
configure Job's env), not just `zuno-demo.internal`/
`svc.cluster.local` - `ansible/roles/keycloak`'s Ingress requests a
cert-manager cert for a public-facing hostname (`keycloak.<domain>`),
which Vault's PKI role would otherwise reject as out of domain.

## Identities and the root token (ADR-0602 clause 1 / WP-223)

- **Unseal**: AWS KMS, from the four `zuno_vault_kms_*` values of
  `ansible/confidential.yml` (the IAM credentials go to the `vault-aws-kms`
  Secret, the key ARN and region into the Application's values). The role
  stops if any is missing. A restart no longer needs a human.
- **Initialization** (first run only): `vault operator init
  -recovery-shares=3 -recovery-threshold=2`. The JSON (recovery keys and
  root token) is written once to `ansible/vault-recovery-<cluster>.json`
  (mode 0600, gitignored) on the Ansible controller - never to a cluster
  Secret. Move it to the operators' password manager and delete it.
- **Root token**: used once, by `tasks/bootstrap_auth.yml` (through
  `k8s_exec`, never a Secret), to create the `vault-configurator` role, then
  revoked as soon as the configure Job has succeeded.
- **vault-configurator** (ServiceAccount `vault-configure`): the configure
  Job's identity - policies, auth, mounts, PKI, Transit keys, audit; no
  access to `zuno/data/*`.
- **ansible-seeder** (ServiceAccount `ansible-seeder`): every seed/read task
  in `ansible/` logs in with `ansible/tasks/vault_login.yml` and uses
  `zuno_vault_token` (create/read/update on the KV, read on `pki/cert/ca`,
  1h TTL).
- **raft-snapshot** (ServiceAccount `vault-raft-snapshot`): the chart's raft
  snapshot CronJob.

A Vault initialized before WP-223 (file storage, Shamir key and root token
in `vault-bootstrap-credentials`) is refused by `install.yml`; migrate it
with `ansible/playbooks/vault_migrate_kms_raft.yml`
(`docs/platform/vault-kms-raft-migration.md`).

`install.yml` also generates and seeds the secrets that can be
self-generated (Keycloak admin, PostgreSQL app credentials, MariaDB root
and the mlops pipeline's metadata-DB password). The rest require external input: the Google Workspace OAuth
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
<item>`, the paths `platform/vault/secret-access.yaml` grants per namespace.
