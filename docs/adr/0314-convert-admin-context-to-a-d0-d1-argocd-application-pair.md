# ADR-0314: Convert `admin_context` to a `-d0`/`-d1` ArgoCD Application pair

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-10
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0312 closed the operator-install exception bucket so that every
installed component is owned by exactly one ArgoCD `Application`, but it
explicitly left two components applying raw manifests directly via
`ansible/tasks/apply_kustomize.yml` (ADR-0310): `argocd` and
`admin_context`. Both were described as "a bootstrap chicken-and-egg no
`Application` can resolve" - the `zuno` `AppProject` every
`Application.spec.project` references doesn't exist until the `argocd`
role has installed the OpenShift GitOps operator, waited for its CRDs, and
applied the `AppProject` itself.

That framing no longer holds for `admin_context`. `ansible/playbooks/
day0_install.yml` and `day0_check.yml` run `day0_components` in order
`argocd`, `admin_context`, `namespaces`, ... (`day0_uninstall.yml` reverses
it: `admin_context` before `argocd`) - a reordering made for unrelated
reasons (`4251f7c change install sequence and argocd config`) that
incidentally guarantees the `zuno` `AppProject` already exists by the time
`admin_context`'s `install.yml`/`precheck.yml` runs. `admin_context`'s own
`README.md` still claimed it ran "first... before argocd," which was stale
relative to the actual playbook order.

Separately, a new requirement arose: register the `startx` Helm chart
repository (`http://sx-helm-repository-prod.s3-website.eu-west-3.amazonaws.com/stable`)
as a cluster-scoped OpenShift `HelmChartRepository`
(`helm.openshift.io/v1beta1`), so it shows up in the Developer Catalog. This
is distinct from the existing ArgoCD-native repository `Secret`
(`ansible/roles/argocd/kustomize/appproject/repository-startx.yaml`), which
only lets ArgoCD itself resolve `startx` chart *dependencies* (e.g.
`cluster-nfd`, `cluster-gpu`) at render time - the two serve different
consumers and both stay. Adding this as a second static, cluster-scoped
resource under `admin_context` was the concrete trigger for revisiting
whether the exception was still justified.

## Decision

`admin_context` becomes a standard `-d0`/`-d1` Application pair, backed by
a new `gitops/charts/admin-context` chart, following the exact pattern
ADR-0312 established for `nfd`/`nvidia_gpu`/`openshift_ai`/
`external_secrets`/`keycloak`/`postgresql`:

- `zuno-admin-context-d0` renders the four `PriorityClass` objects
  (`zuno-platform-critical`/`-important`/`-weak`/`zuno-workload-default`),
  content and names unchanged from the kustomize manifests they replace -
  several charts already reference these names in `priorityClassName`
  fields and must not see them disappear even transiently.
- `zuno-admin-context-d1` renders the new `startx` `HelmChartRepository`.
- `ansible/roles/admin_context/tasks/install.yml` keeps its StorageClass
  discover-and-fail-fast precondition (a legitimate Ansible-side gate, not
  a static manifest) but replaces the `apply_kustomize.yml` call with two
  `ansible/tasks/apply_gitops_app.yml` includes. `precheck.yml` and
  `uninstall.yml` are rewritten around `check_gitops_app_state.yml` and
  `delete_gitops_app.yml`, matching every other converted role (e.g.
  `smtp`). `ansible/roles/admin_context/kustomize/` is deleted.

`argocd` remains the sole permanent exception: it installs the operator
that creates the `AppProject` CRD itself, and no reordering can resolve
that specific chicken-and-egg (the `AppProject` CR needs the CRD, which
needs the operator, which is what `argocd`'s own `install.yml` installs).

No change to `Makefile`, `day0_install.yml`, `day0_check.yml`, or
`day0_uninstall.yml`'s component ordering - `admin_context`'s position was
already correct for this conversion before this ADR; this ADR only changes
what runs inside that position.

## Alternatives considered

- **Leave `admin_context` as the raw-kustomize exception and add the
  `HelmChartRepository` as a third static manifest applied the same way.**
  Rejected: it would perpetuate an exception whose stated justification
  (the AppProject chicken-and-egg) no longer applies, and every other Day 0
  role's state-check/uninstall logic already leans on the
  `check_gitops_app_state.yml`/`delete_gitops_app.yml` helpers that a
  kustomize-based role can't use - keeping `admin_context` on the old path
  means it alone lacks Synced/Healthy-based drift detection.
- **Reorder `admin_context` before `argocd` again** (matching the stale
  README's claim) to keep the "runs before argocd" property some future
  reader might expect. Rejected: nothing in this repository actually
  depends on that ordering - the role's own `install.yml` already treats
  the ArgoCD `ClusterRoleBinding`'s absence as expected-not-error, purely
  defensively - and reverting it would reopen the exact chicken-and-egg
  this ADR closes.

## Consequences

`ansible/roles/admin_context/kustomize/` is removed. `gitops/apps/
README.md`'s "remaining exceptions" list shrinks to `argocd` alone (plus
`vault`'s separately-noted imperative unseal). `ansible/roles/
admin_context/tasks/{install,precheck,uninstall}.yml` shrink to
Application registration/check/delete, mirroring `smtp`'s role.
`gitops/charts/admin-context` and `gitops/apps/admin-context/` are new
directories. `admin_context`'s `README.md` is corrected to no longer claim
it runs before `argocd`.

## Security considerations

No new privilege: `admin_context`'s Applications run under the same
`zuno` `AppProject`/ArgoCD application-controller `ClusterRoleBinding`
every other component's Applications already use. The `HelmChartRepository`
CR only registers a chart index URL for the Developer Catalog to read; it
grants no cluster access beyond what any authenticated user browsing the
catalog already has.

## Operational considerations

On an already-bootstrapped cluster, the first `make d0 install
admin-context` after this change adopts the four existing
`zuno-ansible`-labeled `PriorityClass` objects under `argocd` (label
flips from `zuno.io/managed-by: zuno-ansible` to `zuno.io/managed-by:
argocd`, matching every other GitOps-rendered resource) and additionally
creates the `startx` `HelmChartRepository`, which didn't exist before.
`make d0 uninstall admin-context` now deletes via the two `Application`s'
cascade finalizer rather than direct `PriorityClass` deletes.

See [Standard clauses](README.md#standard-clauses) for Migration/evolution.

## Related ADRs

- [ADR-0312](0312-route-operator-installs-through-argocd-applications.md) (the operator-install conversion whose stated `admin_context`
  exception this ADR closes)
- [ADR-0310](0310-manage-static-kubernetes-resources-as-per-role-kustomize-directories.md) (the kustomize-per-role pattern this replaces for
  `admin_context`; still governs `argocd`, the remaining exception)
- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md) (original Day 0/Day 1 split establishing this role's position
  and purpose)
- [ADR-0313](0313-move-day1-schema-jobs-and-llm-provider-secrets-behind-argocd.md) (the prior ADR narrowing the exception list the same way, for
  the two Day 1 imperative-Job cases it closed)

## Review evidence

Grounded in a direct read of `ansible/playbooks/{day0_install,day0_check,
day0_uninstall}.yml` (confirming `argocd` precedes `admin_context` on
install/check and follows it on uninstall), `ansible/roles/admin_context/
tasks/*.yml` and its `kustomize/priorityclasses/*.yaml`, `ansible/roles/
{cert_manager,smtp}/tasks/*.yml` and `gitops/apps/{cert-manager,smtp}/
application-d{0,1}.yaml` as the pattern templates, `ansible/tasks/
{apply_gitops_app,check_gitops_app_state,delete_gitops_app}.yml`, the
`zuno` `AppProject` (`ansible/roles/argocd/kustomize/appproject/
appproject.yaml`) and its `repository-startx.yaml` sibling, and
`gitops/apps/README.md`'s documented exception list and directory table -
confirmed via `grep -rn "admin_context/kustomize\|kustomize/priorityclasses"`
that no other file in the repository references the removed kustomize
path.
