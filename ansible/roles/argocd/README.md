# argocd

Installs the OpenShift GitOps (ArgoCD) operator, then (once its CRDs are
Established) the zuno `AppProject` every `gitops/apps/*/application-{d0,d1}.yaml`
targets instead of ArgoCD's built-in "default" AppProject
(`ansible/roles/argocd/kustomize/appproject/`) - both in `install.yml`.
This lives here rather than in `admin_context` (which runs first in the
Day 0 sequence, before this role has had a chance to install the operator
and its CRDs) for exactly that reason. `uninstall.yml` deletes the
AppProject before tearing down the operator's own CRDs (per
`ansible/tasks/remove_operator.yml`), so the explicit delete always runs
while the CRD is still present.

This role owns no downstream Application of its own (ADR-0311): every
other component's `install.yml` applies its own child Application
directly (see `ansible/tasks/apply_gitops_app.yml`), which is what turns
a bare cluster-admin token into a fully configured platform, one
component at a time.

The root App-of-Apps (`gitops/root-app-of-apps.yaml`) still exists in the
repository as a documented example of a pure-GitOps, Ansible-free bootstrap
(see `docs/platform/installation.md`), but no `make day0|d0`/`day1|d1`
target ever applies it.

Runs first among prerequisite components - see
`ansible/playbooks/day0_{check,install}.yml`.

## Operator upgrades and health

The Subscription is on a version channel (`gitops-1.22`) with `Manual` approval, so an upgrade of
the operator starts only when its InstallPlan is approved. `make d0 check argocd` runs
`platform/gitops/check_gitops_operator.py` and fails on a failed InstallPlan, a CSV left
`Replacing` or `Pending`, a Subscription on `latest` with `Automatic` approval (set
`zuno_argocd_allow_moving_channel: true` in the cluster file to accept it), or an ArgoCD pod that is not
Ready or restarted in the last 15 minutes. Background: demo333 kept a failed 1.21.4 -> 1.22.0 upgrade for
13 days, unreported, because the old operator kept running.
