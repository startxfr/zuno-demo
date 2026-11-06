# Secrets Management

Vault is the target application secret store. Git contains only secret references and non-secret configuration. Credentials, refresh tokens and provider keys must never be committed.

Workloads never read Vault directly: the External Secrets Operator syncs Vault-held values into namespaced Kubernetes `Secret` objects via one `SecretStore` per namespace, each limited by its own Vault role to the keys `platform/vault/secret-access.yaml` grants that namespace (ADR-0602 clause 2; `platform/vault/check_secret_access.py` enforces it). No `ClusterSecretStore` exists. Workload and service-mesh TLS certificates are issued by cert-manager from a Vault-backed `ClusterIssuer`, not stored as static secrets.
