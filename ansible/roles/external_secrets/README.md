# external_secrets

Applies the `gitops/apps/external-secrets` ArgoCD Application (ADR-0312),
whose chart (`gitops/charts/external-secrets`) installs the External
Secrets Operator and registers the `ClusterSecretStore` every
`ExternalSecret` in the platform resolves against. Backed by the demo
Vault instance (`ansible/roles/vault`), which must already be
initialized, unsealed and have the Kubernetes auth method + `eso-reader`
role configured (see `ansible/roles/vault/tasks/configure.yml`) before
this role's `configure` step runs - enforced by ordering in
`ansible/playbooks/{precheck,install,configure,uninstall}.yml`. Previously
applied raw manifests directly via `ansible/tasks/apply_kustomize.yml`
(ADR-0310); converted to this role-applies-one-Application pattern by
ADR-0312. `zuno-ai-run`'s `Namespace` is owned by `gitops/charts/
namespaces` instead (ADR-0312) - this role no longer re-declares it.

No application secret is ever written directly into a Kubernetes `Secret`
or an Ansible variable file; every workload consumes credentials through an
`ExternalSecret` resolving from this store. See ADR-0024.

## Two-phase apply (ADR-0312)

The chart's `Namespace`s/`Subscription` (sync-wave `"10"`) and
`OperatorConfig` operand (sync-wave `"20"`) are applied by `tasks/
install.yml`'s single `apply_gitops_app.yml` call. The `ClusterSecretStore`
(sync-wave `"30"`) and cluster-domain `ExternalSecret` (sync-wave `"40"`)
are deliberately left unrendered by that call (`gitops/charts/
external-secrets/values.yaml`'s `vaultServiceName` stays unset) and only
applied by `tasks/configure.yml`'s own `apply_gitops_app.yml` call, once
Vault's own `configure` step has prepared the Kubernetes auth method +
`eso-reader` role they depend on - this two-phase split enforces the
Vault-readiness ordering the paragraph above describes; sync-wave alone
cannot (ArgoCD has no way to know about a *different* Application's
readiness). `configure.yml` re-discovers the operator's catalog/channel
(cheap, idempotent) alongside the newly-discovered Vault client `Service`
name, since `gitops_app_extra_helm_values` replaces the Application's
Helm values wholesale (ADR-0048) rather than merging.
