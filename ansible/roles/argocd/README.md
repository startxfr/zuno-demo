# argocd

Installs the OpenShift GitOps (ArgoCD) operator. This role has no
`configure` phase (ADR-0311): every other component's `configure` step
applies its own child Application directly (see
`ansible/tasks/apply_gitops_app.yml`), which is what turns a bare
cluster-admin token into a fully configured platform, one component at a
time.

The root App-of-Apps (`gitops/root-app-of-apps.yaml`) still exists in the
repository as a documented example of a pure-GitOps, Ansible-free bootstrap
(see `docs/platform/installation.md`), but no `make day0|d0`/`day1|d1`
target ever applies it.

Runs first among prerequisite components - see
`ansible/playbooks/day0_{check,install,configure}.yml`.
