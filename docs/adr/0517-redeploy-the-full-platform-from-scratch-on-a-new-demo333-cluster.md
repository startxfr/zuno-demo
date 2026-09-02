# ADR-0517: Redeploy the full platform from scratch on a new demo333 cluster

- **Status:** Proposed
- **Target:** v0.8
- **Date:** 2026-08-24
- **Decision owners:** Zuno Demo architecture team

## Context

The platform's Day 0–3 automation (Ansible + GitOps, ADR-0003/ADR-0030/
ADR-0056/ADR-0060) has only ever been exercised as incremental changes
against the existing `demo222` cluster. There is no direct evidence the
stack can be bootstrapped unattended, end-to-end, on a brand-new cluster —
any residual manual step, undocumented prerequisite, or environment-
specific assumption baked into `demo222` over time would only surface on a
genuine from-scratch run.

## Decision

1. Provision a new OpenShift cluster, `demo333`. Provisioning mechanics
   (infrastructure, base OpenShift install) are an operator decision, out
   of scope for this ADR.
2. Redeploy the full platform onto `demo333` using only the existing entry
   points — `make day0 install`, `make day1 install`, and the existing
   Day 2/Day 3 checks and stresstests. No manual `kubectl`/`oc` patches,
   no undocumented pre-seeding beyond `ansible/confidential.yml`.
3. Any step that requires manual intervention, an undocumented
   prerequisite, or a hand-edited resource is logged in this ADR's
   Implementation notes and either (a) fixed in the Ansible/GitOps
   automation before being marked closed, or (b) filed as its own
   follow-up ADR/WP when the fix is out of scope for this pass.
4. Success is demonstrated by `demo333` passing the same Day 0/Day 1/
   Day 2 acceptance gates (ADR-0053, ADR-0057/ADR-0058) as `demo222`,
   proving the automation — not just the design — is complete.
5. (Added 2026-09-02.) The remediation work this ADR implies is bounded to
   the nine blockers enumerated under *Known blockers* below. Anything
   found beyond them during the run falls under clause 3 — logged, then
   fixed or deferred to a follow-up ADR/WP. B1–B9 are carried by WP-118
   (added 2026-09-02); the run itself stays blocked until `demo333` exists.

## Acceptance criteria

- A real `demo333` cluster exists and the full platform is deployed on it
  via `make day0/day1 install` only.
- `make d1 check` / `make d2 check` / `make d3 test all` pass on `demo333`
  at a rate comparable to `demo222`, or every gap is enumerated here with
  a closure plan.
  (Corrected 2026-09-02: this criterion originally read `make day2 test
  all`, a command that has never existed since ADR-0060 moved the test
  tier from Day 2 to Day 3. `DAY2_VERBS` in the Makefile carries no `test`
  verb, so the criterion was untestable as written.)
- Every manual intervention required during the redeploy is recorded in
  this ADR with either a landed automation fix or a linked follow-up
  ADR/WP.
- `demo222` is left untouched — this is a parallel proof, not a migration.

## Known blockers (audit 2026-09-02)

A static audit of the repository was run ahead of the redeploy to replace
"we will find out by running it" with a bounded list. The result is that
the canonical mechanism is sound and cluster-agnostic by construction:
`ansible/tasks/resolve_cluster_base_domain.yml` discovers the domain from
`Ingress.config.openshift.io/cluster`, and `ansible/tasks/apply_gitops_app.yml`
substitutes the `apps.mycluster.example.com` token into the Application
manifest before applying it. The Makefile, everything under `gitops/apps/`,
the Ansible role logic, the Go operator and all components are clean.

The blockers are exactly the places that bypass that mechanism:

| # | Blocker | Location | Effect on `demo333` |
|---|---|---|---|
| B1 | `cluster.id: demo222-kpkqk`, security group, subnet names, pinned AMI, region | `gitops/charts/machines/values.yaml:27,28,93-96,155-158,197-200` | "no security group found" — zero GPU nodes; Day 0 step 9 (`machines`) hangs waiting for machines to become available |
| B2 | Key is `appsDomain`, not `clusterBaseDomain`, so the token substitution never reaches it | `gitops/charts/grafana/values.yaml:74`, `kiali/values.yaml:60`, `tempo/values.yaml:62` | Tempo's Jaeger UI Route rejected (host outside the cluster wildcard); Kiali serves a dead `web_fqdn`; Grafana trace links point at the old cluster |
| B3 | Full URLs frozen into the acceptance-gate values | `gitops/charts/mlops/values.yaml:135-136` | The ADR-0053 acceptance gate authenticates against the **old** cluster's Keycloak and frontend |
| B4 | `demoHostname` frozen | `gitops/charts/connectivity-link/values.yaml:61` | Kuadrant quota-demo Route on a hostname that does not exist |
| B5 | Four `gp3-csi` StorageClass defaults | `models/values.yaml:296`, `postgresql/values.yaml:71`, `mariadb/values.yaml:105`, `grafana/values.yaml:85` | Breaks if `demo333` is not AWS or names its default class differently; PVC `storageClassName` is immutable once bound |
| B6 | Route53 `hostedZoneID: Z3HY376RT1N9S1`, `region: eu-west-3`, ACME contact email | `gitops/charts/cert-manager/values.yaml:41,54,55` | ACME DNS-01 cannot solve if `demo333` sits under a different parent DNS zone |
| B7 | The vault role reads `zuno_salesforce_instance_url` / `zuno_salesforce_token`; `confidential.example.yml:81-82` supplies `zuno_salesforce_url` / `zuno_salesforce_access_token` | `ansible/roles/vault/tasks/install.yml:998-1003` | The `zuno/salesforce/technical` seed **silently never runs** — the `!= 'xxxxxx'` guard sees an undefined variable, so there is no error, just an unpopulated Vault path |
| B8 | `zuno_mariadb_backup_s3_access_key_id` / `_secret_access_key` are read but appear nowhere in `confidential.example.yml` | `ansible/roles/vault/tasks/install.yml:1061-1065` | Undocumented prerequisite; a fresh install has no way to know the keys exist |
| B9 | Drifted RHOAI InstallPlan — the only `auto_fix: "manual only"` on the install path | `ansible/roles/openshift_ai/tasks/install.yml:90` | Most likely blocker of all: a new cluster's catalog publishes a newer CSV than the pinned `startingCSV`, and reconcile refuses to approve drifted InstallPlans |

Delivery constraint for B1–B6, which must be respected whenever they are
fixed: every `gitops/apps/*/application-*.yaml` points at
`targetRevision: main` with `selfHeal: true`, so ArgoCD renders each chart
from git `main`, not from the operator's working copy. Changing a chart
`values.yaml` default is therefore a **live `demo222` change**, applied at
the next sync. Each literal has to be removed in two steps: first pin the
real value at the Application level (inline `helm.values` or the role's
`gitops_app_extra_helm_values`), which leaves the rendered output
byte-identical; only then flip the chart default to the placeholder.
Doing it in the other order rewrites live Route hosts, which are
effectively immutable.

## Implementation notes

*(empty — no run has been attempted yet; `demo333` does not exist.)*

One entry per manual intervention, added as the run proceeds:

- **Symptom** — what was observed, and at which Day/component.
- **Command** — the manual command that unblocked it.
- **Resolution** — either the automation fix that landed (commit), or the
  follow-up ADR/WP it was deferred to, per Decision clause 3.

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Consequences, Security/Operational considerations, Migration/evolution and
Review evidence.

## Related ADRs

- [ADR-0003](0003-use-ansible-and-make-as-the-deployment-entry-point.md)
- [ADR-0030](0030-use-a-command-dispatch-makefile-interface.md)
- [ADR-0053](0053-make-make-check-an-end-to-end-acceptance-and-security-gate.md)
- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md)
- [ADR-0057](0057-introduce-day-2-agent-availability-test-and-stresstest-operations.md)
- [ADR-0058](0058-aggregate-existing-test-content-into-a-bulk-interaction-stresstest.md)
- [ADR-0060](0060-restructure-day-0-day-1-day-2-day-3-deployment-sequencing.md)
- [ADR-0352](0352-run-day-0-platform-services-in-internal-or-external-mode.md)
