# admin_context

Cluster-admin-level objects every other Day 0 component implicitly
depends on. Runs right after `argocd` in the Day 0 sequence
(`ansible/playbooks/day0_install.yml`), so the `zuno` `AppProject` argocd's
own `install.yml` applies is always in place before this role registers its
own ArgoCD Applications.

This role is a standard `-d0`/`-d1` Application pair like every other
Day 0 component, backed by `gitops/charts/admin-context`:

- `zuno-admin-context-d0` renders the four `PriorityClass` objects:
  `zuno-platform-critical` (value `1000000`, for operators/shared
  infrastructure that must not be preempted), `zuno-platform-important`
  (value `10000`, for platform infrastructure that's needed but not in
  the critical failure path), `zuno-workload-default` (value `100`, for
  agent/business workloads) and `zuno-platform-weak` (value `1`, for
  best-effort/transient platform jobs).
- `zuno-admin-context-d1` renders the `startx` `HelmChartRepository`
  (`helm.openshift.io/v1beta1`), registering the startx Helm repo in the
  cluster's Developer Catalog - separate from the ArgoCD-native repository
  `Secret` (`ansible/roles/argocd/kustomize/appproject/repository-startx.yaml`)
  that lets ArgoCD itself resolve startx chart dependencies.

Task files:

- `precheck.yml` - state detection, never fails: reports whether both
  Applications are Synced+Healthy, setting `admin_context_state_installed`
  and a line in the shared `/tmp` state report (see
  `ansible/playbooks/day0_check.yml`).
- `install.yml` - verifies at least one `StorageClass` exists (discover-
  only, fails with a clear diagnostic if none does), applies both
  Applications via `ansible/tasks/apply_gitops_app.yml`, and reports on
  the `zuno-argocd-application-controller-admin` `ClusterRoleBinding` the
  `argocd` role creates - a visibility check, not a new grant.
- `uninstall.yml` - deletes both Applications via
  `ansible/tasks/delete_gitops_app.yml`, `d1` then `d0`.
