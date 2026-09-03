# WP-118: Close the demo333 portability blockers recorded in ADR-0517

- **State:** Done (2026-09-03 — all nine blockers closed, every flip applied live on
  `demo222` and verified inert). B6 closed last: the three Route53 values moved into
  `ansible/confidential.yml` and the chart flipped to placeholders. Three audit errors were
  corrected along the way: ADR-0517's B7 row described a defect that did not exist in a way
  that would have caused an outage if acted on; step 2's planned MachineSet selector would
  have made the role bootstrap from its own output; and step 3's first inertia test passed
  while comparing two empty renders. No `demo333` cluster exists, so this closes the known
  literals, not the claim that the automation bootstraps — that is ADR-0517's own run.
- **ADRs:** ADR-0517 (Proposed, v0.8)
- **Depends on:** nothing. Blocked by nothing — the ADR-0517 run itself is blocked on
  an operator provisioning `demo333`, but every blocker below is fixable without it.
- **Related:** ADR-0211 (the ACME track whose two consumer flips were silently reverted
  by the same class of defect, fixed 2026-09-02 in `17e4117c`/`8c11ceb1`)

## Goal

Make every chart default cluster-agnostic, so that a from-scratch `make day0/day1
install` on a new cluster is a test of the automation rather than a test of how many
`demo222` literals someone remembers to edit. ADR-0517 bounds the work to the nine
blockers it records; this WP closes them.

## Why this is not just a find-and-replace

The canonical mechanism is already sound and cluster-agnostic:
`ansible/tasks/resolve_cluster_base_domain.yml` discovers the domain from
`Ingress.config.openshift.io/cluster`, and `ansible/tasks/apply_gitops_app.yml`
substitutes the `apps.mycluster.example.com` token into the Application manifest before
applying it. The Makefile, everything under `gitops/apps/`, the Ansible role logic, the
Go operator and all components are already clean. The blockers are the places that
bypass that mechanism, and each needs routing back onto it rather than a new value.

The delivery constraint matters more than the edits. Every
`gitops/apps/*/application-*.yaml` points at `targetRevision: main` with
`selfHeal: true`, so ArgoCD renders each chart from git `main`, not from the operator's
working copy. **Changing a chart `values.yaml` default is a live `demo222` change**,
applied at the next sync. Each literal therefore comes out in two steps:

1. Pin the real value at the Application level (inline `helm.values`, or the role's
   `gitops_app_extra_helm_values`). Rendered output stays byte-identical. Run the
   component's install on `demo222` so the live Application carries it.
2. Only then flip the chart default to the placeholder.

Doing it in the other order rewrites live Route hosts, which are effectively immutable.

## Steps

### Step 1 — domain literals (B2, B3, B4) — **DONE 2026-09-02**

Five charts bypass the token because they use a differently-named key or embed the
domain mid-string: `grafana/values.yaml:74`, `kiali/values.yaml:60`,
`tempo/values.yaml:62` (all `appsDomain`, never substituted), `mlops/values.yaml:135-136`
(full `keycloakUrl`/`frontendUrl`), `connectivity-link/values.yaml:61` (`demoHostname`).

Two call sites need the value re-supplied in the role rather than the manifest, because
their `gitops_app_extra_helm_values` replaces the block wholesale: `connectivity_link`'s
d1 apply, and `grafana`, which applies d1 **twice** — factor a shared base-values fact,
as `lightspeed_config/tasks/install.yml:99` already does.

Also rewrite the comments in `grafana/values.yaml` and `tempo/values.yaml`: they
advertised the anti-pattern this step removes, and cited ADR-0517 for it — wrong twice,
since the citing code belongs to the run_id tracing work whose ADR was never written.

Landed as two commits, in the order the delivery constraint demands: `5c7ca097`
(step 1a, tokens at the Application level, proven inert — all five substitute to
exactly the value the chart default already carried), then the five Applications
re-applied live (`make d1 install` for kiali/tempo/grafana, `make d2 install mlops`,
`make d2 install agents` for connectivity-link-quota, all five Synced/Healthy after),
then `b749d384` (step 1b, chart defaults flipped). grafana needed a role change too:
it applies d1 twice and the second apply replaces the values block, so it dropped
`appsDomain` the moment the manifest declared it — caught by this morning's
`gitops_values_clobber` check, its first real save.

### Step 2 — AWS infra identity (B1) — **DONE 2026-09-03, live-verified**

`gitops/charts/machines/values.yaml` hardcodes `cluster.id: demo222-kpkqk`, the security
group, three subnet names, a pinned AMI and the region. This one cannot use token
substitution: `machineSet.list` is a list (Helm replaces lists wholesale) and Helm cannot
template a dependency subchart's `values.yaml`. It comes from the role via
`gitops_app_extra_helm_values` instead.

**Correction to the audit's plan.** It said to select installer MachineSets on
`machine.openshift.io/cluster-api-machine-role=worker`. That is wrong — our own GPU sets
carry that label too, so the role would have bootstrapped from its own output. The
distinguishing label is `machine.startx.io/group`, which the `cluster-machine` subchart
stamps on everything it renders; the correct source is `Infrastructure/cluster` for the id
and region, plus **any MachineSet lacking** that label. Verified live: four installer sets
lack it, our three carry it.

**2a (landed).** New `ansible/tasks/resolve_cluster_aws_identity.yml` reads the id and
region from `Infrastructure/cluster`, and the AMI, security-group name and an
availability-zone→subnet map from the installer sets. Read, not derived from a pattern:
the installer's naming changed across OCP versions (4.16+ CAPA names the worker SG
`{id}-node`; older installs used `{id}-worker-sg`, still the subchart's default and absent
here), so a pattern is a guess and a live MachineSet is a fact. The first `securityGroups`
entry is taken deliberately — the second is `{id}-lb`, which only API-target machines need.

The chart stays the authoring surface: `machines/tasks/install.yml` **reads
`machineSet.list` from `values.yaml` on every run** and replaces only the four identity
fields per entry, so editing an instance type or a taint in the chart still works.

Three guards, because this is the edit that can prune live GPU MachineSets:
1. the d0 values start from `application-d0.yaml`'s own values, so the three
   `enabled` toggles come along by construction;
2. an explicit `assert` refuses to apply unless all three toggles are true **and** the
   list still has as many entries as the chart declares;
3. a pre-flight failure if any declared AZ has no installer MachineSet to read a subnet
   from — the gap ADR-0517's risk list calls out. Inventing `{id}-subnet-private-{az}`
   would render a MachineSet AWS rejects at first boot, hours later.

Inertia proven before commit, and this is the test that matters: `helm template` of the
chart with the role-built values is **byte-identical** to the render with the manifest
values alone — 5 resources, 3 MachineSets, ClusterAutoscaler, MachineAutoscaler. Discovery
returns `demo222-kpkqk` / `eu-west-2` / `demo222-kpkqk-node` / `ami-00667f67a54be771a` and
the two subnets, each equal to the literal it replaces.

Also avoided: `community.general.json_query` is unusable here (jmespath is not installed
and the filter fails at run time, not at lint time). Same for the dotted-path `selectattr`
trap recorded under step 3.

**2b — DONE 2026-09-03, live-verified.** `make d0 install machines` ran first
(`changed=1`, all Synced/Healthy): `zuno-machines-d0` now carries `cluster.id`,
`cluster.region` and each entry's `ami`/`securityGroupName`/`subnet_name`, with all three
enable toggles and all three MachineSets intact, and the live MachineSets byte-unchanged
by the apply. Only then were the chart literals flipped to `mycluster-*` placeholders
(`8d51c74d`). ArgoCD has since synced `zuno-machines-d0` to a revision containing that
commit — confirmed with `merge-base --is-ancestor`, because "MachineSets unchanged" proves
nothing until the new chart has actually rendered — and the three MachineSets still match
the pre-apply baseline exactly. One `demo222` string survives in the file, in a comment
recording which installer MachineSet `zuno-gpu-c` replaced.

### Step 3 — StorageClass and DNS (B5, B6) — **DONE 2026-09-03, live-verified**

Four `gp3-csi` defaults (`models:296`, `postgresql:71`, `mariadb:105`, `grafana:92` — the
audit said 85) and cert-manager's Route53 `hostedZoneID`/`region`/ACME email.

**3a (landed).** New `ansible/tasks/resolve_cluster_default_storage_class.yml`, mirroring
`resolve_cluster_base_domain.yml`: it reads the class annotated
`storageclass.kubernetes.io/is-default-class`, fails hard rather than guessing when there
is not exactly one (PVC `storageClassName` is immutable once bound), and takes a
`zuno_cluster_storage_class` override. Wired into the five applies that render PVCs —
models d1, postgresql d1, mariadb d1, grafana's second d1, and **both** blocks in
postgresql's `restore.yml`, since each replaces `spec.source.helm.values` wholesale and
omitting it there would silently revert the install value.

One trap cost a rewrite and is worth recording: the obvious
`selectattr('metadata.annotations.storageclass\.kubernetes\.io/is-default-class', ...)`
**silently returns `[]`**. Jinja splits a `selectattr` path on `.` and Ansible honours no
escape, so an annotation whose own name contains dots is unreachable that way. It reads
correctly, raises nothing, and would have failed all five installs with "found 0 default
StorageClasses" on a cluster that has exactly one. Use a loop with a quoted subscript.

B6 follows the same shape: `cert_manager`'s d1 apply now merges an `acme` identity whose
three values default to **the chart file itself** rather than being restated in Ansible,
so there is one source of truth and the apply stays inert until an operator sets
`zuno_certmanager_route53_hosted_zone_id` / `_region` / `zuno_certmanager_email`. Those are documented
as optional in `confidential.example.yml`, extending the existing Route53 IAM block —
non-secret (a public hosted zone ID is a published DNS fact) but per-environment.

Inertia proven before commit: the discovery task run live against `demo222` returns
exactly `gp3-csi`; `helm template` with each key injected, **with the Application's own
toggle enabled**, is byte-identical to the current render on all four charts (3+1+1+1
`storageClassName` lines actually rendered — with the toggles off the charts render no
PVC at all, so a naive diff would have "passed" while testing nothing). The cert-manager
identity resolves to the chart's own `dev+zuno-acme@startx.fr` / `eu-west-3` /
`Z3HY376RT1N9S1`.

**3b — B5 and B6 both DONE 2026-09-03, live-verified.**

B5: the five applies ran (`d0 cert-manager`, `d0 postgresql`, `d1 mariadb`, `d1 grafana`,
`d2 models`), each Application now carries `gp3-csi` discovered from the annotation, and
**all 15 PVCs** across `zuno-data`/`zuno-monitoring`/`zuno-ai-run`/`zuno-ai-build` are
unchanged. The four chart defaults were then flipped (`f4e70bb4`) to
`mycluster-default-storageclass` — deliberately an *invalid* class name, not a plausible
one: `storageClassName` is immutable once bound, so if an Application ever lost its values
a PVC that cannot bind is a loud failure where a plausible name would silently bind to the
wrong storage. Each flipped chart rendered against its own live Application emits `gp3-csi`
and zero placeholders.

B6 — **DONE 2026-09-03.** The ACME identity landed first (`zuno-cert-manager-d1` carries
`acme.route53.{hostedZoneID,region}` and `acme.email`; both Let's Encrypt ClusterIssuers
stayed Ready through the apply, production issuer and both consumer flips intact). The
chart could not be flipped while the role still treated it as its default source, so the
three values moved into `ansible/confidential.yml` — non-secret (a hosted zone ID is a
published DNS fact) but per-environment. Re-applied: **`changed=0`**, the cleanest possible
inertia proof — the value now comes from `confidential.yml` and produces a byte-identical
result. Only then were the chart defaults replaced with placeholders.

The variables were renamed `zuno_acme_*` → `zuno_certmanager_*` before being written, at
the operator's request and for a reason worth recording: `zuno_aws_route53_*` (the IAM
credentials that WRITE the DNS records, destined for Vault) and the new keys (which say
WHERE to write them, destined for the chart) sat one word apart in the same file, and the
operator had already misread one for the other. The chart comment now names the distinction
explicitly, along with the trap that the zone ID must match the zone the IAM policy is
scoped to — otherwise DNS-01 gets AccessDenied while every other check passes.

### Step 4 — undocumented prerequisites (B7, B8) — **DONE 2026-09-02**

The audit's description of B7 was wrong, and following it would have caused an
outage. `ansible/roles/vault/tasks/install.yml` held **two identically-named tasks**
writing `zuno/salesforce/technical`: one at l.940 with keys `url`/`access_token`,
reading the documented variables and running fine; one at l.1001 with keys
`instance_url`/`token`, reading undocumented variables and therefore inert. Because
`vault kv put` replaces rather than merges, documenting the missing variables would
have started the dead task and wiped the keys `mcp-salesforce` serves Comage from.
The two consumers disagreed: `gitops/charts/mcp-salesforce` (live) expects
`url`/`access_token`; `rag-ingestion`'s `domains.sales` (`enabled: false`, deferred to
v0.7 by ADR-0218) expected `instance_url`/`token`.

Resolved by making `url`/`access_token` the single canonical schema: the duplicate seed
task is gone, and `gitops/charts/rag-ingestion/values.yaml`'s `instanceUrlProperty` /
`tokenProperty` now point at it. The ExternalSecret template was already parameterised
on those two values, so it did not change, and the `SALESFORCE_INSTANCE_URL` /
`SALESFORCE_TOKEN` env names are preserved — `components/rag-ingestion` is untouched.
Nothing needed re-running live: Vault already holds the right keys.

B8 was understated rather than wrong. All **five** `zuno_mariadb_backup_s3_*` variables
are undocumented (`ansible/roles/mariadb/tasks/install.yml:98-104`), not just the two
secrets, and none is present in the live `confidential.yml` — so `backups.s3.enabled`
is false, the ExternalSecret is never rendered, and **no MariaDB backup schedule
exists**. Documented as a full block in `confidential.example.yml`, next to the
PostgreSQL repo2 family, naming both traps that family does not share: the
`_access_key_id`/`_secret_access_key` variable suffixes, and the camelCase Vault
properties. `mariadb/s3` was deliberately **not** added to the expected-paths loop at
`install.yml:1167` — the placeholder writer after it would stamp `_placeholder=true`,
and the five sibling S3 paths are absent from it for the same reason.

Also corrected in the same pass: `ansible/roles/mariadb/README.md`'s claim that a
`make d0 install vault` re-run rotates every generated secret. True when written
2026-08-12, false since ADR-0345 added `ansible/tasks/vault_seed_if_missing.yml` the
next day. The stale paragraph discouraged a now-safe operation.

### Step 5 — RHOAI InstallPlan drift (B9) — **DONE 2026-09-03**

The deliverable was a decision, and the decision is **keep the gate**.
`ansible/roles/openshift_ai/tasks/install.yml:90` refuses to approve an InstallPlan whose
CSV differs from the pinned `startingCSV`. That refusal is not the blocker, it is the
reproducibility guarantee this whole ADR exists to establish — auto-approving whatever a
catalog happens to serve is how a platform stops being redeployable. `beta` is a moving
channel (it published `3.5.0-ea.2` when ADR-0002 pinned it; `eus-3.5` already carries the
`3.5.0` GA), so a later-provisioned `demo333` will legitimately be offered something else,
and choosing which build to run stays a human decision.

What was wrong is *when* the operator finds out: mid-install, after the Subscription has
landed, an hour into Day 0. Fixed by detecting it in `precheck.yml` instead, from the
**PackageManifest** — which needs no Subscription and is readable the moment the
CatalogSource is ready. The pin is read from `gitops/charts/openshift-ai/values.yaml`
rather than the live Subscription for the same reason: on a fresh cluster there is neither.
Read-only and never-failing per precheck's contract; it records a finding whose `solution`
names the exact `subscription.version` value to set. Verified on `demo222`: pin
`rhods-operator.3.5.0-ea.2` equals the `beta` channel head, so it reports ALIGNED and
records nothing.

Residual manual step, accepted and bounded: one deliberate version choice before Day 0,
surfaced by `make d0 check` rather than by a failure. Pinning `subscription.operator.channel`
to a fixed channel such as `eus-3.5` instead of `beta` is the obvious follow-up if the
churn ever costs more than it buys.

## What NOT to touch

The Makefile, `gitops/apps/` beyond adding substitution tokens, the Go operator, the
Go/Python components, `realm-zuno.json`, and the secret/S3 configuration surface — all
already cluster-agnostic. The persona emails `dev+zuno-*@startx.fr` and vendor links are
demo data, not cluster identity, and stay.

## Verification checklist (operator steps — ask before running)

- `helm template` each touched chart: no `apps.demo222`, no `demo222-kpkqk`.
- `helm template` with the role-injected values, diffed against the current render:
  **empty diff** expected on `demo222` for Steps 1 and 2 — that is the inertia test.
- `git grep -nE 'apps\.demo222|demo222-kpkqk|ami-00667f67a54be771a|Z3HY376RT1N9S1' -- gitops ansible`
  returns only comment lines.
- `oc get sc` on `demo222` confirms the annotated default really is `gp3-csi` **before**
  Step 3 — PVC `storageClassName` is immutable once bound.
- `make d0 install machines --check --diff`, plus before/after comparison of
  `oc get applications.argoproj.io zuno-machines-d0 -o jsonpath='{.spec.source.helm.values}'`.

### Live applies that gate steps 2b and 3b (operator action — ask first)

Each makes an Application carry the discovered value, so the chart default stops being
what renders. Verified day mapping (this repo puts `cert-manager`, `machines` and
`postgresql` in Day 0, not Day 1):

| Blocker | Command |
|---|---|
| B1 | `make d0 install machines` |
| B6 | `make d0 install cert-manager` |
| B5 | `make d0 install postgresql`, `make d1 install grafana`, `make d1 install mariadb`, `make d2 install models` |

**Sequence `make d2 install models` deliberately, or defer it.** Re-syncing
`zuno-models-d1` recreates the three `Replace=true` lmeval cache-prefetch Jobs, each
re-pulling ~318 MB plus the lmes-job image onto whatever node they land on. On 2026-09-03
that was measured at 22 seconds from Job creation to `EvictionThresholdMet` on a
schedulable master already at 85% of its image filesystem. Run it when the cluster is not
under disk pressure.
- `python3 platform/docs/check_docs.py` passes.

## Risks and known unknowns

- Step 2 can prune live GPU MachineSets if the toggles are dropped from the dict.
- Step 3 is unrecoverable-by-sync if `demo222`'s default StorageClass is not `gp3-csi`.
- The AMI is region- and OCP-version-scoped; deriving it from a live MachineSet is
  correct for a cluster that already has one, but says nothing about an AZ where no
  installer MachineSet exists. Expect an operator override path.
- Nothing here is exercised until a real `demo333` exists. A green audit is evidence
  that the known literals are gone, not that the automation bootstraps.

## Status updates

Per the five-copy rule: ADR-0517 body, `docs/adr/README.md`, the tracker row, this
brief and `MEMORY.md` move together, and `check_docs.py` must pass, before this is Done.
