# ADR-0311: Stop applying the root App-of-Apps from Ansible bootstrap tasks

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-06
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0022's "Bootstrap architecture" addendum (2026-08-04) had
`make day0 configure argocd` apply `gitops/root-app-of-apps.yaml` - a
recursive ArgoCD App-of-Apps over `gitops/apps/` - in `ansible/roles/
argocd/tasks/configure.yml`, *in addition to* every other Day 0/Day 1
role independently applying its own child Application via
`ansible/tasks/apply_gitops_app.yml`. That shared task's own header
comment already named the redundancy explicitly: "Applying the
Application here is safe even though the root App-of-Apps also recurses
over gitops/apps/: both paths converge on the same desired state."

That convergence assumption is not free. `ansible/roles/vault/tasks/
install.yml` carries a live incident report of it failing: naming the
Vault Application `{{ zuno_id }}-vault` (this repository's usual
per-role convention) instead of matching `gitops/apps/vault/
application.yaml`'s own static `zuno-vault` name created a *second*,
independent Vault release/StatefulSet on a real cluster
(api.demo222.startx.fr) once the root App-of-Apps also synced the
static file under its own name - two ArgoCD-owned reconciliation paths
for what was assumed to be one desired state. More generally, the root
App-of-Apps' `syncPolicy.automated.prune: true` makes it capable of
touching or pruning any child Application under `gitops/apps/` the
moment its own recursive read of a `application.yaml` disagrees with
what `apply_gitops_app.yml` just rendered (e.g. mid-way through that
task's `cluster_base_domain`/extra-Helm-values substitution) - a race
between two independent appliers of the same resource, not a safety net.

An explicit operator decision was made to drop this redundancy for the
Ansible-driven Day 0/Day 1 phases, while keeping the App-of-Apps pattern
available as a worked example for anyone who wants a pure-GitOps,
Ansible-free bootstrap.

## Decision

`ansible/roles/argocd/tasks/configure.yml` no longer applies
`gitops/root-app-of-apps.yaml`. It becomes a documented no-op, matching
the existing convention already used by `nfd`/`nvidia_gpu`/
`observability`/`smtp`'s `configure.yml` (PREP-only components with
nothing left to configure). `ansible/roles/argocd/tasks/uninstall.yml`
no longer deletes the `zuno-app-of-apps` Application, since nothing
applies it anymore.

Every platform component continues to be installed/reconciled
exclusively through its own role's direct `apply_gitops_app.yml` call -
already this repository's mechanism for keeping a single-component
`make day0|d0 configure <component>` / `make day1|d1 configure|run
<component>` self-sufficient without a full sync (ADR-0022) - which is
now the *only* path, not one of two.

`gitops/root-app-of-apps.yaml` is not deleted. It stays in the
repository and is documented in `docs/platform/installation.md` as the
manifest to apply by hand (`oc apply -f gitops/root-app-of-apps.yaml`)
for an operator who wants a pure-GitOps, Ansible-free install/demo path,
and as a worked example of the App-of-Apps pattern for anyone extending
`gitops/apps/`. No `make day0|d0`/`day1|d1` target applies it, and it is
not exercised by `make check` or CI.

This amends the "Bootstrap architecture" addendum in
[ADR-0022](0022-use-gitops-managed-declarative-agent-tasks-and-policies.md);
ADR-0022's original decision (agent tasks/policies GitOps-managed and
reviewable in Git) is unaffected.

## Alternatives considered

- Keep both paths (status quo). Rejected: the vault-naming incident is a
  real, not hypothetical, case of the "both paths converge" assumption
  failing; the redundancy was meant as a safety net but behaves as a
  second, competing owner instead.
- Delete `gitops/root-app-of-apps.yaml` outright. Rejected per an
  explicit operator decision to keep it as a documentation example of
  the App-of-Apps pattern.
- Have Ansible keep applying the App-of-Apps but with
  `automated.prune: false` / no `selfHeal`. Rejected: a non-automated
  App-of-Apps buys nothing `apply_gitops_app.yml` doesn't already do
  per-component, while still requiring a human to remember to trigger
  its sync - added surface for no behavior gained.

## Consequences

`make day0 configure argocd` / `make day0 all` no longer create or wait
on a `zuno-app-of-apps` Application. Every `gitops/apps/*` component's
desired state is owned by exactly one applier (its own role's
`apply_gitops_app.yml` call), removing the dual-ownership/prune-race
class of failure the vault incident demonstrated. Operators following
`docs/platform/installation.md`'s manual App-of-Apps example get a
second, independent way to reach the same end state - explicitly marked
as documentation-only, not exercised by any automated target.

## Security considerations

No authorization surface changes: `apply_gitops_app.yml` already applied
every Application with the same `kubernetes.core.k8s` credentials the
App-of-Apps' own sync would have used. Removing the redundant path
narrows, rather than widens, the set of ways cluster state can change.

## Operational considerations

An operator with a live cluster from before this change should confirm
no orphaned `zuno-app-of-apps` Application is still `Synced` in
`openshift-gitops`; if so, remove it once by hand
(`oc -n openshift-gitops delete application zuno-app-of-apps`) - nothing
in this repository re-creates it. `ansible/roles/argocd/tasks/
uninstall.yml` and its header comment were updated to match: it now only
removes the operator's own Subscription/ClusterRoleBinding.

See [Standard clauses](README.md#standard-clauses) for Migration/evolution.

## Related ADRs

- ADR-0022 (amends its "Bootstrap architecture" addendum)
- ADR-0056

## Review evidence

This decision follows a direct operator instruction to stop routing Day
0/Day 1 Ansible tasks through the App-of-Apps, keeping it solely as an
install-documentation example. Grounded in a direct read of
`ansible/roles/argocd/tasks/{configure,uninstall}.yml`,
`ansible/tasks/apply_gitops_app.yml`'s existing "both paths converge"
comment, and `ansible/roles/vault/tasks/install.yml`'s existing comment
recording the real dual-ownership incident on api.demo222.startx.fr that
this decision resolves.
