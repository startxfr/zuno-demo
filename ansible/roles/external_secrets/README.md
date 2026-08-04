# external_secrets

Installs the External Secrets Operator and registers the
`ClusterSecretStore` every `ExternalSecret` in the platform resolves
against. Backed by the demo Vault instance (`ansible/roles/vault`), which
must already be initialized, unsealed and have the Kubernetes auth method +
`eso-reader` role configured (see `ansible/roles/vault/tasks/configure.yml`)
before this role's `configure` step runs - enforced by ordering in
`ansible/playbooks/{precheck,prepare,configure}.yml`.

No application secret is ever written directly into a Kubernetes `Secret`
or an Ansible variable file; every workload consumes credentials through an
`ExternalSecret` resolving from this store. See ADR-0024.
