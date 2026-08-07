# admin_context

Cluster-admin-level objects every other Day 0 component implicitly
depends on (ADR-0056). Positioned first in the Day 0 sequence, before
`argocd`.

- `install-precheck.yml`/`configure-precheck.yml` - state detection, never
  fail: report whether the two PriorityClasses already exist, setting
  `admin_context_state_installed`/`_state_configured` and a line in the
  shared `/tmp` state report (see `ansible/playbooks/day0_check.yml`).
  `configure` mirrors `install` here - this role has nothing else of its
  own to configure (the zuno `AppProject` this role used to own moved to
  the `argocd` role - see that role's README for why).
- `install.yml` - verifies at least one `StorageClass` exists (discover-
  only, never invents provisioner-specific parameters - fails with a
  clear diagnostic if none does), and applies two `PriorityClass` objects:
  `zuno-platform-critical` (value `1000000`, for operators/shared
  infrastructure) and `zuno-workload-default` (value `100`, for agent/
  business workloads).
- `configure.yml` - re-applies both PriorityClasses (idempotent) and
  reports on the `zuno-argocd-application-controller-admin`
  `ClusterRoleBinding` the `argocd` role creates - a consolidation/
  visibility point, not a new grant. This binding legitimately doesn't
  exist yet the first time `configure` runs here (admin_context runs
  before argocd in the Day 0 sequence), so its absence is reported, not
  failed on.

No other role in this repository creates a `ClusterRoleBinding` today, so
there is nothing else to consolidate yet - if a future Day 0 component
needs its own cluster-scoped binding, add it there and note it here.
