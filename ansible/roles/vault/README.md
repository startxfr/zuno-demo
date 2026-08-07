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
self-generated (Keycloak admin, PostgreSQL app credentials) and reserves
empty placeholders - never overwriting a real value - for the two secrets
that genuinely require an operator to supply external input: the Google
Workspace OAuth client (ADR-0014) and the SMTP technical-mail credentials.
