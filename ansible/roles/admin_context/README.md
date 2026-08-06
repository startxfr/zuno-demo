# admin_context

Cluster-admin-level objects every other Day 0 component implicitly
depends on (ADR-0056). Positioned first in the Day 0 sequence, before
`argocd`.

- `install-precheck.yml` - state detection, never fails: reports whether
  the two PriorityClasses already exist, setting
  `admin_context_state_installed` and a line in the shared `/tmp` state
  report (see `ansible/playbooks/day0_check.yml`). Does not check the
  zuno `AppProject` - see why below.
- `configure-precheck.yml` - same, but reports whether the zuno
  `AppProject` exists, setting `admin_context_state_configured`.
- `install.yml` - verifies at least one `StorageClass` exists (discover-
  only, never invents provisioner-specific parameters - fails with a
  clear diagnostic if none does), and applies two `PriorityClass` objects:
  `zuno-platform-critical` (value `1000000`, for operators/shared
  infrastructure) and `zuno-workload-default` (value `100`, for agent/
  business workloads). It deliberately does NOT apply the zuno
  `AppProject` (see `configure.yml` below).
- `configure.yml` - re-applies both PriorityClasses (idempotent), then
  waits for the `AppProject` CRD (`appprojects.argoproj.io`) to be
  Established and applies the zuno `AppProject` every
  `gitops/apps/*/application.yaml` targets - it can't be applied from
  `install.yml` because that CRD doesn't exist until the `argocd` role's
  own `install.yml` has subscribed the GitOps operator, and `make d0
  install` runs every component's `install.yml` (argocd included) before
  any `configure.yml`, so the CRD is guaranteed to exist by the time this
  runs. Also reports on the `zuno-argocd-application-controller-admin`
  `ClusterRoleBinding` the `argocd` role creates - a consolidation/
  visibility point, not a new grant. This binding legitimately doesn't
  exist yet the first time `configure` runs here (admin_context runs
  before argocd in the Day 0 sequence), so its absence is reported, not
  failed on.

No other role in this repository creates a `ClusterRoleBinding` today, so
there is nothing else to consolidate yet - if a future Day 0 component
needs its own cluster-scoped binding, add it there and note it here.
