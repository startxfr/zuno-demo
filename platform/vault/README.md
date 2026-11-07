# Platform: vault

Vault prerequisite and application secret integration.

## Per-namespace secret access (ADR-0602 clause 2, WP-223)

- `secret-access.yaml`: which Vault keys (relative to the KV v2 mount `zuno`)
  each namespace may read. One `SecretStore` named `vault` per namespace logs
  in with the Vault role `ns-<namespace>`, whose policy grants only those keys.
- `check_secret_access.py`: renders every `gitops/apps` Application and the
  ExternalSecrets Ansible applies, and fails on a `ClusterSecretStore`, a key
  not granted to its namespace, a namespace without exactly one store, or an
  unused grant. `--inventory` prints what each namespace actually reads.
  Run in CI (`.github/workflows/lint.yml`, helm job).
