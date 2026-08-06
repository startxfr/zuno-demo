# ADR-0312: Route openshift_ai/nfd/nvidia_gpu/external_secrets through ArgoCD Applications

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-06
- **Decision owners:** Zuno Demo architecture team

## Context

`gitops/apps/README.md` has, since ADR-0310, documented an explicit exception:
"operators with no standalone workload of their own (`argocd`,
`external_secrets`, `nvidia_gpu`, `openshift_ai`) are installed by direct
`kubernetes.core.k8s` Subscription/CR tasks in their own Ansible role
instead ... since an OLM `Subscription` + operator-managed CR has no
meaningful 'chart' to template." In practice this means four roles apply
raw manifests (`Namespace`, `OperatorGroup`, `Subscription`, the
operator's own CR) through `ansible/tasks/apply_kustomize.yml` and a
per-role `kustomize/` directory (ADR-0310), instead of through the
`gitops/apps/<component>/application.yaml` + `gitops/charts/<component>`
+ `ansible/tasks/apply_gitops_app.yml` pattern every other Day 0/Day 1
component already uses.

An explicit operator decision was made to close this exception: every
installed component, including the OLM `Subscription` itself, should be
owned by exactly one ArgoCD `Application`, consistent with the rest of
the platform. `openshift_ai` was the component cited as the motivating
example (it also duplicates the `zuno-ai-run` `Namespace` object already
owned by `gitops/charts/namespaces` - a second, independent issue fixed
as part of this same change), but `nfd`, `nvidia_gpu` and
`external_secrets` share the identical Namespace+OperatorGroup+
Subscription+operand-CR shape, so all four are converted together rather
than repeating this exercise four times.

`argocd` and `admin_context` are **not** converted - `argocd` installs
ArgoCD itself, and `admin_context` creates the `AppProject` (`zuno`) every
`Application.spec.project` in this repository references. Both are a
bootstrap chicken-and-egg no `Application` can resolve. `sql_schema` and
`rag`'s one-shot SQL `Job`s, `vault`'s imperative unseal, and the
`*_build` roles' `BuildConfig`s are likewise out of scope - they are
one-shot actions, not standing installed components, and none of them
duplicate an object another chart already owns.

### The Subscription/CR ordering problem

Applying an OLM `Subscription` and its operand CR (e.g.
`DataScienceCluster`) through the *same* `Application` means ArgoCD must
not attempt to sync the CR before OLM has installed the CSV that
registers its CRD - otherwise the sync fails with "no matches for kind
X". `argocd.argoproj.io/sync-wave` already exists in every
`application.yaml`/chart template in this repository, but purely as
App-of-Apps ordering documentation (ADR-0311: Ansible-driven applies
ignore it). Making the wave gate actually work within a single
Application's own sync requires ArgoCD to know when a `Subscription` is
"done" - and this repository has never registered a custom health check
for `operators.coreos.com/Subscription` (ArgoCD's default health
evaluation reports any resource kind it has no health logic for as
`Healthy` immediately after a successful apply, which is not true of a
`Subscription` still mid-install).

## Decision

1. **Custom ArgoCD health check.** `ansible/roles/argocd/tasks/
   install.yml` now patches the operator-managed `ArgoCD` CR
   (`openshift-gitops`/`openshift-gitops`, auto-created by the OpenShift
   GitOps operator - this repository never created it itself) with a
   `spec.resourceHealthChecks` entry for `operators.coreos.com/
   Subscription`: `Healthy` once `status.installedCSV` is set and the
   referenced CSV's `status.phase` is `Succeeded`, `Degraded` if
   `CatalogSourcesUnhealthy` is `True`, `Progressing` otherwise. Patching
   the `ArgoCD` CR (not the `argocd-cm` `ConfigMap` directly) is required
   because the operator reconciles `argocd-cm` *from* that CR - a direct
   `ConfigMap` edit would be overwritten on the operator's next
   reconcile. Registered in `install.yml`, not `configure.yml`: `make
   day0|d0 all` runs every component's `install.yml` before any
   component's `configure.yml` (two separate full passes over
   `day0_components`), and the four converted roles' own `install.yml`
   already depend on this health check existing.

2. **Two-wave chart convention.** Each converted chart's templates carry
   `argocd.argoproj.io/sync-wave`: `"10"` for the `Namespace`/
   `OperatorGroup`/`Subscription`, `"20"` for the operand CR. With (1) in
   place, ArgoCD does not attempt wave 20 until wave 10 reports `Healthy`.

3. **Runtime-discovered values stay in Ansible, passed through
   `gitops_app_extra_helm_values`** (the existing ADR-0048 mechanism,
   already used by `models`), not hand-edited into checked-in chart
   values: `openshift_ai`'s catalog-published channel, `external_secrets`'
   catalog/channel and the discovered Vault client `Service` name. These
   are all resolvable *before* the Subscription exists (catalog
   introspection or a prior role's output), so a single
   `apply_gitops_app.yml` call per role covers them.

4. **`nvidia_gpu` is the one genuine two-phase case.** Its
   `ClusterPolicy` spec is read from the *installed* CSV's own
   `alm-examples` (ADR-0047/ADR-0310's existing reasoning: every
   OLM-published operator ships its own recommended default CR, more
   reliable than a hand-maintained spec) - information that does not
   exist until OLM has finished installing the operator the Subscription
   requests. `nvidia_gpu`'s `install.yml` therefore calls
   `apply_gitops_app.yml` **twice**: once with no extra values (renders
   only the wave-10 `Namespace`/`OperatorGroup`/`Subscription`, chart's
   `clusterPolicy` template is conditional on `.Values.clusterPolicy.spec`
   being set), waits for it `Healthy`; then discovers the installed CSV's
   `alm-examples` exactly as before, and calls `apply_gitops_app.yml`
   again with `gitops_app_extra_helm_values: {clusterPolicy: {spec:
   <discovered>}}`, which updates the same `Application`'s Helm values
   and lets ArgoCD sync the now-populated wave-20 `ClusterPolicy`. The
   role never applies the `ClusterPolicy` manifest itself - both calls go
   through the same shared task an `Application` update, not a
   `kubernetes.core.k8s` apply of the CR.

5. **`zuno-ai-run` `Namespace` ownership moves entirely to
   `gitops/charts/namespaces`.** `openshift_ai` no longer creates this
   `Namespace` (it only adds the `opendatahub.io/dashboard: "true"` label
   and the GPU `ResourceQuota`, both folded into `gitops/charts/
   namespaces`' own `values.yaml`/templates as an `openshiftAi` values
   block); `external_secrets` no longer re-declares it either. This
   removes the two-Applications-managing-one-`Namespace` overlap found
   while investigating this conversion - the same class of problem
   ADR-0311 already fixed once for `vault`.

6. **Uninstall** switches from deleting each raw manifest to
   `ansible/tasks/delete_gitops_app.yml`, followed by the existing
   `ansible/tasks/remove_operator.yml` (ArgoCD's prune does not clean up
   the CSV OLM's catalog installed - that has always required this
   separate step, unchanged by this ADR).

This amends [ADR-0310](0310-manage-static-kubernetes-resources-as-per-role-kustomize-directories.md)
for these four roles only; ADR-0310 remains the governing pattern for
`admin_context`, `argocd`, `sql_schema`/`rag`'s one-shot Jobs, and the
`*_build` roles.

## Alternatives considered

- Keep the `Subscription` imperative in Ansible (matching `keycloak`/
  `postgresql`'s existing operator-imperative/operand-declarative split)
  and only move the operand CR to ArgoCD. Rejected per an explicit
  operator decision: the goal stated for this change was that a role
  "should limit itself to creating an ArgoCD Application," not a
  partial move - and `keycloak`/`postgresql` were not in scope for
  reconsideration here.
- Register the health check as a raw `argocd-cm` `ConfigMap` patch.
  Rejected: the OpenShift GitOps operator reconciles that `ConfigMap`
  from the `ArgoCD` CR's spec and would revert an out-of-band edit.
- Give `nvidia_gpu`'s chart a Helm lookup/hook to read the CSV's
  `alm-examples` itself instead of a second Ansible-side
  `apply_gitops_app.yml` call. Rejected: ArgoCD explicitly discourages
  Helm's `lookup` function for values that must be known at render time
  in a GitOps-reconciled chart (non-deterministic diffs between renders,
  no dependency the sync-wave graph can express) - keeping the discovery
  in Ansible, which already has this exact logic, is the smaller change.

## Consequences

`gitops/apps/README.md`'s exception list shrinks to `argocd` alone.
`openshift_ai`, `nfd`, `nvidia_gpu`, `external_secrets` each gain a
`gitops/apps/<component>/application.yaml` and a `gitops/charts/
<component>/`, and lose their `ansible/roles/<role>/kustomize/`
directory. `gitops/charts/namespaces` gains an `openshiftAi` values
block (dashboard label + GPU quota). First sync of any of these four
components now visibly spends time `Progressing` (wave 10, waiting on
OLM) before wave 20 renders - previously invisible to ArgoCD since
Ansible drove that wait directly; `apply_gitops_app.yml`'s existing
`Synced`+`Healthy` wait already tolerates this, no change needed there.

## Security considerations

The new `spec.resourceHealthChecks` Lua patch runs inside ArgoCD's
existing Lua sandbox (no new privilege) and only reads `.status`/
`.metadata` fields already visible to ArgoCD's cluster-read RBAC.
`kubernetes.core.k8s` credentials used to apply each `Application` are
unchanged from what previously applied the same objects directly - no
new authorization surface.

## Operational considerations

An operator with a live cluster from before this change should confirm
no orphaned raw `Subscription`/`OperatorGroup`/CR objects remain
unmanaged by ArgoCD after the first `make d0 configure
openshift-ai|nfd|nvidia-gpu|external-secrets` run - the new `Application`
adopts the existing objects by name (no unnecessary churn), but a
`zuno-ai-run` `Namespace` previously labeled only by `openshift_ai`'s old
kustomize should be re-checked for the `opendatahub.io/dashboard: "true"`
label after `gitops/charts/namespaces` takes over.

## Migration / evolution

Future changes must be documented by a new ADR using `Supersedes
ADR-0312` when applicable.

## Related ADRs

- ADR-0310 (amended, for these four roles only)
- ADR-0311 (established the sync-wave-is-cosmetic-for-Ansible convention
  this ADR partially reverses, by making waves functional within a
  single Application's own sync)
- ADR-0048 (`gitops_app_extra_helm_values` mechanism reused here)
- ADR-0047 (NFD→GPU Operator node-label ordering, unaffected)

## Review evidence

Grounded in a direct read of `gitops/apps/README.md`'s exception list,
`ansible/roles/{openshift_ai,nfd,nvidia_gpu,external_secrets}/tasks/
{install,configure,uninstall}.yml` and their `kustomize/` manifests, and
`ansible/tasks/{apply_gitops_app,apply_kustomize,delete_gitops_app,
remove_operator}.yml`. The `zuno-ai-run` double-ownership (`openshift_ai`
kustomize + `external_secrets` kustomize + `gitops/charts/namespaces`)
was found by comparing all three directly. Follows an explicit operator
instruction to convert all four roles together, with the OLM
`Subscription` itself inside the ArgoCD-managed chart rather than left
imperative.
