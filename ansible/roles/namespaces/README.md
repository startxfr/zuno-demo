# namespaces

Applies the namespace-scaffolding GitOps Applications (`gitops/apps/namespaces`
→ `gitops/charts/namespaces`): the
`zuno-auth`/`zuno-data`/`zuno-monitoring`/`zuno-ai-platform`/`zuno-ai-run`/`zuno-ai-build`/`zuno-mlops`
platform namespaces (`-d0`), each with a `ResourceQuota` and a default-deny
`NetworkPolicy` baseline (`-d1`). Agent workloads no longer get their own
namespace - every active agent's FE/BFF deploys into the shared
`zuno-ai-run` namespace instead. Moved out of `ansible/roles/agents` so
namespace creation is its own explicit, checkable step.

Unlike every other component, this role's `-d0`/`-d1` split spans the
*macro* Day 0/Day 1 boundary, not just Day 0's own internal ordering:
`-d0` (bare Namespace objects, `namespace.enabled: true`) is a Day 0
component so every other Day 0 role can assume the namespaces it deploys
into already exist; `-d1` (`ResourceQuota`/`NetworkPolicy`,
`policy.enabled: true`) is deferred to Day 1 so a bare `make day0 install`
doesn't bundle policy enforcement with cluster bootstrap. The `namespaces`
role is therefore invoked from **both** `ansible/playbooks/day0_*.yml` and
`ansible/playbooks/day1_*.yml`, each selecting a different task file via a
special-cased `tasks_from`:

| Playbook | Component list position | `tasks_from` |
|---|---|---|
| `day0_install.yml` / `day0_check.yml` / `day0_uninstall.yml` | `day0_components` (unchanged position) | `install` / `precheck` / `uninstall` (default - Day 0 half only) |
| `day1_install.yml` / `day1_check.yml` | first in `day1_components` | `install_d1` / `precheck_d1` |
| `day1_uninstall.yml` | last in `day1_components` | `uninstall_d1` |

- `precheck.yml` / `precheck_d1.yml` - state detection, never fails: each
  checks one Application's (`zuno-namespaces-d0` / `zuno-namespaces-d1`)
  Synced+Healthy status and records a line in the shared `/tmp` state
  report (see `ansible/playbooks/day0_check.yml` / `day1_check.yml`).
  `precheck.yml` additionally validates ADR-0333's required namespace
  topology directly against the cluster (`kind: Namespace`, `status.phase:
  Active`) for both the Zuno-managed namespaces this role creates and the
  product-managed namespaces (`redhat-ods-*`, `openshift-ingress*`) it
  doesn't - existence/health only, not workload placement.
- `install.yml` / `install_d1.yml` - applies one GitOps Application each
  (idempotent; re-running gives an explicit on-demand re-sync after a
  `values.yaml` change).
- `uninstall.yml` / `uninstall_d1.yml` - deletes one GitOps Application
  each. Run `make day1 uninstall namespaces` before `make day0 uninstall
  namespaces` so the `-d1` Application isn't left targeting namespaces the
  `-d0` half already removed.

**Tradeoff:** every other Day 0/Day 1 component (`vault`, `cert_manager`,
`external_secrets`, `postgresql`, `keycloak`, `aap`, `smtp`, `nfd`,
`nvidia_gpu`, `observability`, `openshift_ai`) runs after `namespaces`
(ADR-0421 split several of these across Day 0/Day 1, but none of them
carry namespace-policy protection of their own) and comes up with no
quota/network-policy baseline
until `make day1 install namespaces` (or `make day1 install`, which runs
`namespaces` first) is run separately.

`ansible/roles/agents` still exists and still applies the `api` (Tekos
workloads) Applications - it no longer applies this one.
