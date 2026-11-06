# external_secrets

Applies the `gitops/apps/external-secrets` ArgoCD Application, whose
chart (`gitops/charts/external-secrets`) installs the External
Secrets Operator and renders one `SecretStore` named `vault` (with a
`vault-reader` ServiceAccount) in each namespace that reads Vault
(ADR-0602 clause 2, WP-223). Each store logs in with the Kubernetes auth
role `ns-<namespace>`, whose policy grants only the keys listed for that
namespace in `platform/vault/secret-access.yaml`; there is no
`ClusterSecretStore` any more. Namespaces created after this role runs
render their store in their own chart (`cert-manager`, `openclaw`'s
`zuno-claw-*`). Backed by the demo
Vault instance (`ansible/roles/vault`), which must already be
initialized, unsealed and have the Kubernetes auth method + the
per-namespace roles configured (see `ansible/roles/vault/tasks/install.yml`) before this
role's second apply below runs - enforced by ordering in
`ansible/playbooks/day0_{check,install,uninstall}.yml`. `zuno-ai-run`'s
`Namespace` is owned by `gitops/charts/namespaces` instead - this role no
longer re-declares it.

No application secret is ever written directly into a Kubernetes `Secret`
or an Ansible variable file; every workload consumes credentials through an
`ExternalSecret` resolving from this store.

## Two-phase apply

The chart's `Namespace`s/`Subscription` (sync-wave `"10"`) are applied by
`tasks/install.yml`'s first `apply_gitops_app.yml` call. The `OperatorConfig`
operand (sync-wave `"20"`), the per-namespace `ServiceAccount`s and `SecretStore`s (sync-waves `"29"`/`"30"`) and
cluster-domain `ExternalSecret` (sync-wave `"40"`) are deliberately left
unrendered by that call and only applied by a second `apply_gitops_app.yml`
call further down the same file, once `vault` (earlier in
`day0_components`) has prepared the Kubernetes auth method + the
`ns-<namespace>` roles the `SecretStore`s depend on - sync-wave alone can't enforce
this, since ArgoCD has no way to know about a *different* Application's
readiness. The second call sets `operatorconfig.enabled`,
`secretStores.enabled` and the newly-discovered Vault client
`Service` name (`vaultServiceName`), since `gitops_app_extra_helm_values`
replaces the Application's Helm values wholesale rather than merging.
