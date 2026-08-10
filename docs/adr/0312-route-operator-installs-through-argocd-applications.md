# ADR-0312: Route operator installs (openshift_ai/nfd/nvidia_gpu/external_secrets/postgresql/keycloak) through ArgoCD Applications

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
ArgoCD itself (and, once its own CRDs are Established, the `AppProject`
(`zuno`) every `Application.spec.project` in this repository references -
moved here from `admin_context`, which runs before `argocd` in the Day 0
sequence and so can't wait on a CRD that role hasn't installed yet).
Both are a bootstrap chicken-and-egg no `Application` can resolve. `sql_schema` and
`rag`'s one-shot SQL `Job`s, `vault`'s imperative unseal, and the
`*_build` roles' `BuildConfig`s are likewise out of scope - they are
one-shot actions, not standing installed components, and none of them
duplicate an object another chart already owns.

**Extension: `postgresql` and `keycloak`.** These two roles already had
their operand (`PostgresCluster`, `Keycloak`+`KeycloakRealmImport`) in a
chart+Application; only their OLM `Subscription` (+ `OperatorGroup` for
`keycloak`) remained imperative, mirroring the split this ADR's first
version deliberately left unreconsidered. Once the health check/sync-wave
mechanism below existed, extending it to these two was the same pattern
with no new mechanism needed - done as a follow-up in the same ADR rather
than a separate one. `smtp` (a single static `ExternalSecret`, no
operator) and `vault`'s init/unseal/secret-seeding (calls Vault's own API
and captures generated secret material at runtime - no combination of
ArgoCD/Helm can express that) were considered and explicitly rejected:
both stay imperative permanently, not a deferred conversion.

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
   install.yml` patches the operator-managed `ArgoCD` CR
   (`openshift-gitops`/`openshift-gitops`, auto-created by the OpenShift
   GitOps operator) with a `spec.resourceHealthChecks` entry for
   `operators.coreos.com/Subscription`: `Healthy` once
   `status.installedCSV` is set and the referenced CSV's `status.phase`
   is `Succeeded`, `Degraded` if `CatalogSourcesUnhealthy` is `True`,
   `Progressing` otherwise. Patching the `ArgoCD` CR (not the
   `argocd-cm` `ConfigMap` directly) is required because the operator
   reconciles `argocd-cm` *from* that CR. *(Superseded 2026-08-07: still
   registered in `argocd`'s `install.yml` for the same
   `nfd`/`nvidia_gpu`/`openshift_ai`/`external_secrets`-sorts-after-`argocd`
   reason, but now gates the health of the `-d0` Application specifically -
   see point 8 below.)*

2. **Two-wave chart convention.** Each converted chart's templates carry
   `argocd.argoproj.io/sync-wave`: `"10"` for the `Namespace`/
   `OperatorGroup`/`Subscription`, `"20"` for the operand CR. With (1) in
   place, ArgoCD does not attempt wave 20 until wave 10 reports `Healthy`.
   `postgresql` and `keycloak` (the extension above) already had their own
   chart-internal negative sync-wave numbering predating this ADR
   (`postgresql`: `-35`/`-30`; `keycloak`: `-20`/`-15`/`-10`) - their new
   `Subscription`/`OperatorGroup` use `-40`/`-25` respectively (earlier
   than everything already in each chart) rather than renumbering the
   rest to fit `"10"/"20"`. The absolute values differ per chart; the
   invariant that matters is only "operator wave sorts before every
   operand wave in the same chart." *(Superseded 2026-08-07: preserved
   verbatim inside each chart, but the two wave "halves" now render via
   two separate `-d0`/`-d1` Applications instead of via sync-wave ordering
   inside one - see point 8.)*

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
   OLM-published operator ships its own recommended default CR) -
   information that does not exist until OLM has finished installing the
   operator. `nvidia_gpu`'s `install.yml` calls `apply_gitops_app.yml`
   **twice**: once with no extra values (renders only the wave-10
   `Namespace`/`OperatorGroup`/`Subscription`), waits Healthy; then
   discovers the installed CSV's `alm-examples` and calls again with
   `gitops_app_extra_helm_values: {clusterPolicy: {spec: <discovered>}}`.
   The role never applies the `ClusterPolicy` manifest itself. *(Superseded
   2026-08-07: collapses from two calls against one Application to one call
   against `-d0` followed by one call against `-d1` - see point 8.)*

5. **`zuno-ai-run` `Namespace` ownership moves entirely to
   `gitops/charts/namespaces`.** `openshift_ai` no longer creates this
   `Namespace` (it only adds the `opendatahub.io/dashboard: "true"` label
   and the GPU `ResourceQuota`, both folded into `gitops/charts/
   namespaces`' own values/templates); `external_secrets` no longer
   re-declares it either. This removes the two-Applications-managing-one-
   `Namespace` overlap - the same class of problem ADR-0311 already fixed
   once for `vault`.

6. **Uninstall** switches from deleting each raw manifest to
   `ansible/tasks/delete_gitops_app.yml`, followed by the existing
   `ansible/tasks/remove_operator.yml` (ArgoCD's prune does not clean up
   the CSV OLM's catalog installed).

7. **`postgresql`/`keycloak`: the `Application` apply stays in
   `configure.yml`, not `install.yml`.** Unlike the four roles above, both
   these charts' operand renders `ExternalSecret`s resolving against the
   `vault-backend` `ClusterSecretStore`, which only becomes Ready once
   `external_secrets`' own `configure.yml` has run; applying in
   `configure.yml` preserved the ordering these two roles already relied
   on. *(Superseded 2026-08-07: `configure.yml` was merged into
   `install.yml` repo-wide - see point 8 for how the ordering guarantee is
   now provided instead.)*

8. **Addendum (2026-08-07): two later, separate operator decisions
   superseded specific mechanics above (not their reasoning).**
   - *`configure.yml` merged into `install.yml`*: the old two-pass
     `make day0|d0 all` (`run_one install && run_one configure`, a
     separate full pass over `day0_components` for each) was collapsed
     into a single `run_one check && run_one install` pass, with
     `configure`/`run` removed from the Makefile entirely. Point 7's
     ordering guarantee (`external_secrets` before `keycloak`/
     `postgresql`) is now provided by `day0_components`' own sequence
     alone (`vault` → `external_secrets` → `keycloak` → `postgresql`):
     each role's `install.yml` runs to full completion before the next
     starts. Package/channel discovery, previously re-run independently
     by `install.yml` and `configure.yml` because separate
     `ansible-playbook` processes don't share facts, now happens once per
     role. Every role's `tasks/install-precheck.yml` and
     `tasks/configure-precheck.yml` were likewise merged into one
     `tasks/precheck.yml`.
   - *Operator/operand split into separate `-d0`/`-d1` Applications*:
     the operator/operand split this ADR introduced at the `sync-wave`
     level (points 2/4) became explicit at the `Application` level.
     Every component now has two ArgoCD Applications: `<app>-d0`
     (operator install and other cluster-scoped resources - the former
     wave-`"10"`/negative-wave content, gated `operator.enabled`) and
     `<app>-d1` (CRD instances, pods, secrets - the former wave-`"20"`+
     content, gated an operand-specific `<name>.enabled` flag, e.g.
     `nodeFeatureDiscovery.enabled`, `clusterPolicy.enabled`). The
     ordering guarantee that a single Application's own sync-wave retry
     used to provide is now entirely Ansible's: `install.yml` applies
     `-d0` and waits Synced+Healthy before applying `-d1` (the same
     two-call pattern already used for `nvidia_gpu`/`external_secrets`'
     discovery-dependent second apply). The root App-of-Apps
     (`gitops/root-app-of-apps.yaml`, already non-operational per
     ADR-0311) loses this ordering entirely on that path - accepted,
     since it was already documentation-only. Uninstall now spans two
     `delete_gitops_app.yml` calls: `-d1` first (ArgoCD-pruned), then
     `remove_operator.yml`, then `-d0`.
   - Components with no OLM operator at all (`vault`, `agent-runtime`,
     `ai-gateway`, `api`, `llm`, `mcp`, `mcp-sales-db`, `models`, `rag`)
     gained an empty `-d0` Application pointing at a new
     `gitops/charts/noop` chart, and `namespaces` gained an empty `-d1`
     the same way - purely for the uniform `-d0`/`-d1` naming convention,
     not new content. `smtp` and `observability` (previously raw
     kustomize, no `Application` at all) were converted to this same
     chart+toggle+`-d0`/`-d1` pattern in the same change, `observability`
     adopting point 1's health-check mechanism for the first time.

This amends [ADR-0310](0310-manage-static-kubernetes-resources-as-per-role-kustomize-directories.md)
for these six roles only; ADR-0310 remains the governing pattern for
`admin_context`, `argocd`, `sql_schema`/`rag`'s one-shot Jobs, and the
`*_build` roles.

## Alternatives considered

- Keep the `Subscription` imperative in Ansible (the operator-imperative/
  operand-declarative split `keycloak`/`postgresql` originally used) and
  only move the operand CR to ArgoCD. Rejected per an explicit operator
  decision: the goal was that a role "should limit itself to creating an
  ArgoCD Application," not a partial move.
- Register the health check as a raw `argocd-cm` `ConfigMap` patch.
  Rejected: the OpenShift GitOps operator reconciles that `ConfigMap`
  from the `ArgoCD` CR's spec and would revert an out-of-band edit.
- Give `nvidia_gpu`'s chart a Helm lookup/hook to read the CSV's
  `alm-examples` itself instead of a second Ansible-side
  `apply_gitops_app.yml` call. Rejected: ArgoCD explicitly discourages
  Helm's `lookup` function for values that must be known at render time
  in a GitOps-reconciled chart - keeping the discovery in Ansible, which
  already has this exact logic, is the smaller change.

## Consequences

`gitops/apps/README.md`'s exception list shrinks to `argocd` alone.
`openshift_ai`, `nfd`, `nvidia_gpu`, `external_secrets` each gain a
`gitops/apps/<component>/application.yaml` and a `gitops/charts/
<component>/`, and lose their `ansible/roles/<role>/kustomize/`
directory entirely. `postgresql` and `keycloak` keep their existing
`gitops/apps`/`gitops/charts` entries, gain a `Subscription`
(+`OperatorGroup` for `keycloak`) template each, and lose only the
`kustomize/` subdirectories that applied those two objects directly
(`postgresql/kustomize/catalogsource-fallback/` stays - it registers a
cluster-wide OLM catalog, not this component's own workload).
`gitops/charts/namespaces` gains an `openshiftAi` values block (dashboard
label + GPU quota). First sync of any of these six components now
visibly spends time `Progressing` (operator wave, waiting on OLM) before
the operand wave renders - previously invisible to ArgoCD since Ansible
drove that wait directly; `apply_gitops_app.yml`'s existing
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
openshift-ai|nfd|nvidia-gpu|external-secrets|postgresql|keycloak` run -
the new `Application`/updated chart adopts the existing objects by name
(no unnecessary churn), but a `zuno-ai-run` `Namespace` previously
labeled only by `openshift_ai`'s old kustomize should be re-checked for
the `opendatahub.io/dashboard: "true"` label after `gitops/charts/
namespaces` takes over.

See [Standard clauses](README.md#standard-clauses) for Migration/evolution.

## Related ADRs

- [ADR-0310](0310-manage-static-kubernetes-resources-as-per-role-kustomize-directories.md) (amended, for these six roles only)
- [ADR-0311](0311-stop-applying-the-root-app-of-apps-from-ansible.md) (established the sync-wave-is-cosmetic-for-Ansible convention
  this ADR partially reverses, by making waves functional within a
  single Application's own sync)
- [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md) (`gitops_app_extra_helm_values` mechanism reused here)
- [ADR-0047](0047-manage-the-complete-openshift-ai-prerequisite-lifecycle.md) (NFD→GPU Operator node-label ordering, unaffected)

## Review evidence

Grounded in a direct read of `gitops/apps/README.md`'s exception list,
`ansible/roles/{openshift_ai,nfd,nvidia_gpu,external_secrets}/tasks/
{install,configure,uninstall}.yml` and their `kustomize/` manifests, and
`ansible/tasks/{apply_gitops_app,apply_kustomize,delete_gitops_app,
remove_operator}.yml`. The `zuno-ai-run` double-ownership was found by
comparing `openshift_ai`/`external_secrets`/`gitops/charts/namespaces`
directly. Follows an explicit operator instruction to convert all four
roles together; the `postgresql`/`keycloak` extension follows a direct
operator question ("why not these too?") answered by reading both roles'
existing tasks/charts, then an explicit approval to proceed.
