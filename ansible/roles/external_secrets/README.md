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

## External mode (ADR-0352, WP-216)

`zuno_external_secrets_mode: external` in `ansible/confidential.yml` (absent = `internal`) declares that the External
Secrets Operator is installed and lifecycle-managed outside this installer. It is a Tier A-operator component: the
mode key is the whole contract, there is no endpoint and no `_external_*` payload.

| Verb | internal (default) | external |
|---|---|---|
| `install` | applies `zuno-external-secrets-d0` (OLM Subscription), then `-d1` | skips `-d0`; asserts the CRDs (`externalsecrets`, `secretstores`, `clustersecretstores`, `operatorconfigs`), a `Succeeded` CSV `external-secrets-operator*` and the Ready controller `openshift-operators/external-secrets-operator-controller-manager`, failing fast otherwise; then applies `-d1` |
| `check` | SecretStore `zuno-ai-run/vault` Ready | the same, AND the assertion above (record-only) |
| `uninstall` | removes `-d1`, the operator, then `-d0` | removes `-d1` only; the operator, its CSV and Subscription are never touched |

The `-d1` side, the `OperatorConfig` and the per-namespace Vault `SecretStore`s, is ours in both modes: the ESO to Vault
wiring exists whatever the mode of either side.

**Installing the operator outside this installer.** Subscribe `external-secrets-operator` (OLM, `openshift-operators`,
cluster-wide OperatorGroup) from the catalog of your choice, and wait for its CSV to be `Succeeded` and
`external-secrets-operator-controller-manager` to be Ready. Do not create an `OperatorConfig`: `-d1` does, in
`zuno-vault`. Then set the mode and run `make d0 install external-secrets`.

**Flipping the mode** is a migration event, not a reconcile (clause 4). Internal to external: hand the Subscription
over (delete the `zuno-external-secrets-d0` Application without cascade, so the Subscription and CSV stay), then set
`external`. External to internal: set `internal` and run `make d0 install external-secrets`, which re-adopts the
Subscription through `-d0`.
