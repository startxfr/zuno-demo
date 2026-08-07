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
