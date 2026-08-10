# external_secrets

Applies the `gitops/apps/external-secrets` ArgoCD Application (ADR-0312),
whose chart (`gitops/charts/external-secrets`) installs the External
Secrets Operator and registers the `ClusterSecretStore` every
`ExternalSecret` in the platform resolves against. Backed by the demo
Vault instance (`ansible/roles/vault`), which must already be
initialized, unsealed and have the Kubernetes auth method + `eso-reader`
role configured (see `ansible/roles/vault/tasks/install.yml`) before this
role's second apply below runs - enforced by ordering in
`ansible/playbooks/day0_{check,install,uninstall}.yml`. Previously
applied raw manifests directly via `ansible/tasks/apply_kustomize.yml`
(ADR-0310); converted to this role-applies-one-Application pattern by
ADR-0312. `zuno-ai-run`'s `Namespace` is owned by `gitops/charts/
namespaces` instead (ADR-0312) - this role no longer re-declares it.

No application secret is ever written directly into a Kubernetes `Secret`
or an Ansible variable file; every workload consumes credentials through an
`ExternalSecret` resolving from this store. See ADR-0024.

## Two-phase apply (ADR-0312)

The chart's `Namespace`s/`Subscription` (sync-wave `"10"`) are applied by
`tasks/install.yml`'s first `apply_gitops_app.yml` call. The `OperatorConfig`
operand (sync-wave `"20"`), `ClusterSecretStore` (sync-wave `"30"`) and
cluster-domain `ExternalSecret` (sync-wave `"40"`) are deliberately left
unrendered by that call and only applied by a second `apply_gitops_app.yml`
call further down the same file, once `vault` (earlier in
`day0_components`) has prepared the Kubernetes auth method + `eso-reader`
role the `ClusterSecretStore` depends on - this two-phase split enforces
the Vault-readiness ordering the paragraph above describes; sync-wave alone
cannot (ArgoCD has no way to know about a *different* Application's
readiness). Deferring `OperatorConfig` to the second call also avoids a
CRD-registration race: by then the first call's Application has already
gone Synced+Healthy, guaranteeing OLM's CSV install has registered the
`OperatorConfig` CRD. The second call sets `operatorconfig.enabled`,
`clusterSecretStore.enabled` and the newly-discovered Vault client
`Service` name (`vaultServiceName`), since `gitops_app_extra_helm_values`
replaces the Application's Helm values wholesale (ADR-0048) rather than
merging.
