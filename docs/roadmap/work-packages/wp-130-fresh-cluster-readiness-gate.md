# WP-130: Turn the from-scratch failure modes into a Day 0 readiness gate

- **State:** Done (2026-09-04 — seven probes wired into both Day 0 playbooks, silent on `demo222`, each proven able to fire)
- **ADRs:** [ADR-0517](../../adr/0517-redeploy-the-full-platform-from-scratch-on-a-new-demo333-cluster.md)
  (clause 3 — B11 is detected here while WP-132 fixes it),
  [ADR-0547](../../adr/0547-parameterize-every-cluster-specific-value-in-ansible.md)
  (clause 6 — this WP *is* that clause's verification mechanism)
- **Depends on:** [WP-118](wp-118-demo333-portability-blockers.md) (Done — the three
  `resolve_cluster_*.yml` discovery tasks this probe mirrors)
- **Related:** [WP-132](wp-132-cluster-parameterization.md) (parameterizes what this
  probe checks for), [WP-131](wp-131-per-cluster-s3-bucket-convention.md) (B12, which
  probe P6 detects until it lands)

## Goal

Every from-scratch failure mode this platform has today is discovered the same way:
`make d0 install` runs for forty minutes and then a resolver fails hard, mid-role, on a
cluster the operator has already half-built. Move that discovery to `make d0 check`,
where it costs ten seconds and nothing has been applied yet.

ADR-0517 B9 already established both the pattern and the reason. The RHOAI InstallPlan
gate was correct and stayed; what was wrong was *when* the operator learned of it, so the
same fact is now read from the PackageManifest during `precheck` instead of from a
Subscription mid-install. This WP generalizes that single probe into the seven checks a
fresh cluster actually needs.

## Why a shared task file and not a role

`ansible/roles/*` is 1:1 with the Makefile's component lists — `check_day0_day1_roles`
in `platform/docs/check_docs.py` couples `DAY0_COMPONENTS`/`DAY1_RUN_COMPONENTS` to role
directories, and every role carries `precheck`/`install`/`uninstall`. Readiness has no
install, no uninstall, no reconcile and no Application. As a role it would be the only
non-component role in the repository, and adding it to `DAY0_COMPONENTS` to make it
visible would make `make d0 install cluster-readiness` a legal no-op.

`ansible/tasks/*.yml` is the established habitat for shared verb-first files
(`load_k8s_auth_env.yml`, `check_gitops_app_state.yml`, `resolve_cluster_*.yml`,
`record_blocked_finding.yml`). The new file is `ansible/tasks/check_cluster_readiness.yml`
— deliberately not `precheck_*`, since `precheck` is role vocabulary
(`include_role: tasks_from: precheck`).

## Contract: a pure probe

The file sets exactly one fact, `cluster_readiness_findings` — a list of
`record_blocked_finding.yml`-shaped dicts (`component`, `resource`, `state`, `cause`,
`solution`, `auto_fix`) plus one extra key, `blocking: true|false`. It prints one summary
line. It **never calls `record_blocked_finding.yml` itself and never fails.** Callers
dispose of the list.

This mirrors `check_gitops_app_state.yml`, which sets `_state_check_result` and lets its
callers decide, and it is what allows the check path and the install path to treat the
same findings differently without a mode flag.

## The seven probes

| # | Probe | Blocking | Mirrors |
|---|---|---|---|
| P1 | Exactly one StorageClass annotated `is-default-class`, or `zuno_cluster_storage_class` set | yes | `resolve_cluster_default_storage_class.yml` |
| P2 | Platform is AWS; at least one MachineSet lacks `machine.startx.io/group`; every AZ declared in `gitops/charts/machines/values.yaml` has a subnet | yes | `resolve_cluster_aws_identity.yml` |
| P3 | `Ingress/cluster` readable; domain starts with `apps.`; Route53 identity still on the `mycluster` placeholders; `zuno_aws_route53_*` unset | yes, except the `apps.` prefix (advisory) | `resolve_cluster_base_domain.yml` |
| P4 | **B11** — the *resolved* ACME consumer flips are on while `router-wildcard-tls`/`api-server-tls` are absent or not `Ready` | yes | new |
| P5 | `ansible/confidential.yml` present; documented families still unset | presence yes; MariaDB S3 (B8) advisory | `vault/tasks/install.yml:5-19` |
| P6 | **B12** — `zuno_cluster_name` is not the cluster that owns the effective S3 bucket names | yes | new |
| P7 | **ADR-0547 clause 6** — a chart default still carries a `mycluster-*` placeholder that no parameter replaces | yes | new |

P2's AZ check is the gap ADR-0517's own risk list names: the AMI and subnets are read
from installer MachineSets, so an availability zone with no installer MachineSet is
simply absent from the discovered map. Inventing `{id}-subnet-private-{az}` would render
a MachineSet AWS rejects at first boot, hours later.

P6 is the direct protection of ADR-0517's "`demo222` is left untouched" criterion. It
deliberately does **not** presuppose ADR-0546's naming convention, which is still
`Proposed` — it only observes that the effective buckets belong to another cluster. It
simplifies once WP-131 lands.

## Rules that are not stylistic

Each of these corresponds to a mistake already paid for once.

- **Subscript access with a quoted key, never `selectattr` on a dotted path.** Copy the
  form at `resolve_cluster_default_storage_class.yml:39-51`. Jinja splits a `selectattr`
  attribute argument on `.` with no escape Ansible honours, so an annotation whose own
  name contains dots is unreachable that way: it reads perfectly, raises nothing, and
  silently returns `[]`.
- **P2 filters on the absence of `machine.startx.io/group`**, never on
  `cluster-api-machine-role=worker` — our own GPU MachineSets carry that label, so the
  probe would bootstrap from its own output.
- **P5 never registers or prints a secret value.** The scan lives in a task-scoped
  `vars:` entry whose only output is a list of variable *names* and set/unset booleans;
  `include_vars` is not used, because loading `confidential.yml` into play scope at the
  top of `day0_check.yml` would change what every subsequent role precheck sees. **No
  `no_log` anywhere in the file** — the protection is structural (the fact holds no
  values), and a `no_log` here would suppress the one line an operator needs while
  protecting nothing.
- **P5 uses a static family list, not a diff against `confidential.example.yml`.** Most
  of that file's blocks are optional by design; a generic diff would fire on `demo222`
  and destroy the zero-findings acceptance test. Minimum list: the five
  `zuno_mariadb_backup_s3_*` (advisory — B8's lesson is that unset means no backup
  schedule exists at all) and `zuno_aws_route53_access_key_id`/`_secret_access_key`
  (blocking — DNS-01 cannot solve without them).
- **`auto_fix` is a single-line quoted scalar, never a folded `>-` block.**
  `check_auto_fix_commands` reads raw text and would capture `>-` as the value. Values
  starting `manual only` are skipped by the linter, which is what B9 uses. Note the
  asymmetry: `make` commands inside `solution` reach the operator through a Jinja
  variable and are invisible to the linter — verify those by hand.
- The summary `debug` line is linted by `check_debug_make_commands`: either no `make`
  command in it, or only real ones.

## Wiring

**`ansible/playbooks/day0_check.yml`** — between `Initialize blocked-resource tracking`
and `Run Day 0 component state checks`: include the probe, then loop each finding into
`record_blocked_finding.yml`. The extra `blocking` key rides along harmlessly;
`report_blocked_findings.yml` reads only the six documented keys. Placement is after the
accumulator's initialization, because `record_blocked_finding.yml`'s own header warns
that `blocked_findings` must never be shadowed by an include parameter.

**`ansible/playbooks/day0_install.yml`** — after the same initialization and before
`Install Day 0 components`: the probe, then a single `fail` on
`cluster_readiness_findings | selectattr('blocking') | list | length > 0`, rendering
those findings' cause and solution.

Readiness findings deliberately **do not** enter `blocked_findings` on the install path.
`report_blocked_findings.yml` fails the play when `blocked_report_fail` is true, so an
advisory finding — the MariaDB backup keys, which `mariadb/tasks/install.yml:96-116`
treats as legitimately optional — would fail a Day 0 install that otherwise succeeded
completely. That is a regression, not a gate.

Also add `zuno_repo_root: "{{ playbook_dir }}/../.."` to `day0_install.yml`'s play vars,
mirroring `day0_check.yml`. Today it comes from the inventory's `group_vars`, which means
the gate is inert under an AAP Job Template's Controller-managed inventory.

The probe runs **unconditionally**, including for `make d0 check <one-component>`: it is
five read-only API calls and three file reads, and `make d0 check machines` on a fresh
cluster is exactly when the AWS probe is wanted.

## What this WP does not do

It does not flip `consumers.routerDefaultCert`/`apiServerNamedCert` back to `false` in
`gitops/apps/cert-manager/application-d1.yaml`. That is a live `demo222` change
(`targetRevision: main` + `selfHeal: true`) which would regress the ACME track ADR-0211
has just stabilized. B11 is *detected* here and *parameterized* by WP-132.

## Delivered 2026-09-04

`ansible/tasks/check_cluster_readiness.yml`, 30 tasks, included by both
`day0_check.yml` (records every finding into `blocked_findings`) and
`day0_install.yml` (fails on the blocking subset only, before the component
loop). `zuno_repo_root` was added to `day0_install.yml`'s play vars, mirroring
`day0_check.yml` — it normally comes from the inventory's `group_vars`, which an
AAP Job Template's Controller-managed inventory does not have, and the gate would
have been silently un-included there.

**P4's premise changed while this WP was being written.** WP-132 step 3 moved the
ACME rollout state out of `application-d1.yaml` into operator variables and added
a role guard against walking a live track backwards, so "the manifest ships the
flips on" is no longer detectable — there is no manifest value left to read. P4
now resolves the same four variables the role does and asks the remaining
question: are the consumers on while the Certificates they point at do not exist?
That is the mistake available on a *new* cluster, where an operator sets the
variables ahead of the rollout.

**P6 needed one new declaration.** `zuno_s3_bucket_owner_cluster` names the
cluster that owns the buckets in `confidential.yml`. Unset, P6 is silent — it has
nothing to compare. Set, it catches the realistic failure: copying a working
`confidential.yml` onto the new cluster, which is exactly how B12 would happen.
It does not presuppose ADR-0546's naming convention, still `Proposed`, and WP-131
makes it obsolete.

### Proving a silent probe is not a broken probe

`cluster readiness: 0 finding(s), 0 blocking` on `demo222` is the acceptance
test, and on its own it is worth nothing: a probe that returns zero because it is
broken looks identical to one that returns zero because the cluster is fine. So
each condition was driven to fire.

P6 end to end against the live cluster, by declaring a different owner:
`-e zuno_s3_bucket_owner_cluster=demo999` produced
`cluster readiness: 1 finding(s), 1 blocking`, the finding reached
`blocked_findings`, and `report_blocked_findings.yml` printed
`BLOCKED RESOURCES (1)` with its cause and solution. That exercises the
accumulator, the publish, the recording loop and the report in one run.

P1, P2, P4 and P7's conditions were unit-tested against fabricated inputs, and
**the P1 test found a real defect** — in the shipped resolver, not only here.
`resolve_cluster_default_storage_class.yml` compares
`... | default('false') | string == 'true'` and its comment claims `| string`
protects against an annotation that deserializes as a bool. It does not:
`True | string` renders `'True'`, which that comparison silently misses. The API
returns `map[string]string` so it cannot bite through `k8s_info` today, but the
expression was asserting a protection it did not have, in the one place that
hard-fails five installs. Both copies now use `| string | lower`, and the
resolver's comment says what it actually does. Re-verified afterwards: the probe
is still silent and the resolver still returns `gp3-csi`.

## Verification (operator steps — ask before running)

- `ansible-playbook -i ansible/inventories/demo/hosts.yml ansible/playbooks/day0_check.yml --syntax-check`
  and the same for `day0_install.yml`.
- `ansible-playbook -i ansible/inventories/demo/hosts.yml ansible/playbooks/day0_check.yml -e target_component=admin-context`
  — the real loop, since the probe runs unconditionally. Expected on `demo222`:
  `cluster readiness: 0 finding(s), 0 blocking`, and a `blocked_findings` summary
  identical to today's. That is WP-118's inertia test applied to a probe: it must be
  silent on the cluster that already satisfies everything.
- `python3 platform/docs/check_docs.py` passes.
- Each verdict is independently confirmable with `oc get storageclass`,
  `oc get infrastructure/cluster`, `oc get machineset -n openshift-machine-api`,
  `oc get ingress.config.openshift.io/cluster` and `oc get certificate -n cert-manager`.

**Never run `make d0 install` to verify.** The gate's correctness is provable from the
probe's output alone.

Note that `--syntax-check` does not follow an `include_tasks` with a templated path, so
CI's `ansible` job will not syntax-check the new file — the `target_component` run is the
only real check.

## Risks and known unknowns

- A probe that fires on `demo222` is a bug in the probe, not a finding. The zero-findings
  result is the acceptance test, and P5's static family list exists precisely to keep it
  meaningful.
- P6 and P7 encode facts that WP-131 and WP-132 will change; both must be revisited when
  those land rather than left asserting a superseded shape.
- Nothing here is exercised against a genuinely fresh cluster until `demo333` exists. A
  silent probe on `demo222` proves the checks are correctly inert, not that they catch
  what they claim to catch.
