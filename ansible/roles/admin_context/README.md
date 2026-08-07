# admin_context

Cluster-admin-level objects every other Day 0 component implicitly
depends on (ADR-0056). Positioned first in the Day 0 sequence, before
`argocd`.

- `precheck.yml` - state detection, never fails: reports whether the two
  PriorityClasses already exist, setting `admin_context_state_installed`
  and a line in the shared `/tmp` state report (see
  `ansible/playbooks/day0_check.yml`).
- `install.yml` - verifies at least one `StorageClass` exists (discover-
  only, never invents provisioner-specific parameters - fails with a
  clear diagnostic if none does), applies two `PriorityClass` objects:
  `zuno-platform-critical` (value `1000000`, for operators/shared
  infrastructure) and `zuno-workload-default` (value `100`, for agent/
  business workloads), and reports on the
  `zuno-argocd-application-controller-admin` `ClusterRoleBinding` the
  `argocd` role creates - a consolidation/visibility point, not a new
  grant. This binding legitimately doesn't exist yet the first time this
  role runs (admin_context runs before argocd in the Day 0 sequence), so
  its absence is reported, not failed on. The zuno `AppProject` this role
  used to own moved to the `argocd` role - see that role's README for why.

No other role in this repository creates a `ClusterRoleBinding` today, so
there is nothing else to consolidate yet - if a future Day 0 component
needs its own cluster-scoped binding, add it there and note it here.
