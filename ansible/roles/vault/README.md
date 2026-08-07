# vault

Installs Vault (via the `vault` GitOps Application, demo-grade single
replica with file storage), initializes and unseals it, then configures the
Kubernetes auth method and the `eso-reader` policy/role that
`ansible/roles/external_secrets` binds its `ClusterSecretStore` to, plus
the `pki/` secrets engine (a self-signed root CA, `common_name:
zuno-demo.internal`) and the `cert-manager-issuer` policy/role that
`ansible/roles/cert_manager` binds its `ClusterIssuer` to (see that role's
README). Both follow the same shape - a role/policy each consumer's
role only ever *references* declaratively, never configures itself - all
prepared by the same idempotent script,
`ansible/roles/vault/kustomize/unseal-configure/configmap.yaml`.

This is the one role that cannot depend on Vault for its own bootstrap
secret: `install.yml` captures the unseal key and root token into a
Kubernetes `Secret` (`vault-bootstrap-credentials`) in a locked-down,
admin-only namespace (`zuno-vault`) rather than requiring any
external input. See ADR-0024.

`install.yml` also generates and seeds the secrets that can be
self-generated (Keycloak admin, PostgreSQL app credentials). Three more
secrets genuinely require external input and can't be generated: the
Google Workspace OAuth client (ADR-0014), the SMTP technical-mail
credentials, and the Atlassian Confluence technical token. Those come from
`ansible/confidential.yml` - copied from the checked-in
`ansible/confidential.example.yml` and filled in by an operator before the
first `make d0 install vault`, gitignored so no secret is ever written to a
Git-tracked file. `install.yml` re-reads it on every run and (re-)seeds
Vault from it, so the file can be deleted again afterwards unless Vault
needs to be reinstalled. Any of the three left as the example file's
`"xxxxxx"` sentinel instead falls back to an empty Vault placeholder -
never overwriting a real value however it got there.

Vault's KV v2 secrets engine is mounted at `zuno/` (not the HashiCorp
default `secret/`) - every platform secret lives under `zuno/<component>/
<item>`, matching the `eso-reader` policy scope below.
