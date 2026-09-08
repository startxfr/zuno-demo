# ADR-0517: Redeploy the full platform from scratch on a new demo333 cluster

- **Status:** Implemented
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
5. (Added 2026-09-02; extended 2026-09-03.) The remediation work this ADR
   implies is bounded to the blockers enumerated under *Known blockers*
   below. Anything found beyond them during the run falls under clause 3 —
   logged, then fixed or deferred to a follow-up ADR/WP. The list started at
   nine and is now thirteen; each is carried by exactly one work package:
   B1–B9 by WP-118 (added 2026-09-02), B10 by WP-123, B11 by WP-132 with
   detection in WP-130, B12 by ADR-0546 executed by WP-131, and B13 by WP-132.
   (Closed 2026-09-08.) The run happened once `demo333` existed — see
   Implementation notes below for the from-scratch execution itself.

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
| B1 | `cluster.id: demo222-kpkqk`, security group, subnet names, pinned AMI, region | `gitops/charts/machines/values.yaml` | "no security group found" — zero GPU nodes; Day 0 step 9 (`machines`) hangs waiting for machines to become available. **Closed 2026-09-03** (WP-118 steps 2a/2b): discovered from `Infrastructure/cluster` plus any MachineSet lacking `machine.startx.io/group`, injected as Application values, chart flipped to `mycluster-*` placeholders |
| B2 | Key is `appsDomain`, not `clusterBaseDomain`, so the token substitution never reaches it | `gitops/charts/grafana/values.yaml:74`, `kiali/values.yaml:60`, `tempo/values.yaml:62` | Tempo's Jaeger UI Route rejected (host outside the cluster wildcard); Kiali serves a dead `web_fqdn`; Grafana trace links point at the old cluster. **Closed 2026-09-02** (WP-118 step 1): all three routed back onto the `apps.mycluster.example.com` token |
| B3 | Full URLs frozen into the acceptance-gate values | `gitops/charts/mlops/values.yaml:135-136` | The ADR-0053 acceptance gate authenticates against the **old** cluster's Keycloak and frontend. **Closed 2026-09-02** (WP-118 step 1) |
| B4 | `demoHostname` frozen | `gitops/charts/connectivity-link/values.yaml:61` | Kuadrant quota-demo Route on a hostname that does not exist. **Closed 2026-09-02** (WP-118 step 1) |
| B5 | Four `gp3-csi` StorageClass defaults | `models`, `postgresql`, `mariadb`, `grafana` `values.yaml` | Breaks if `demo333` is not AWS or names its default class differently; PVC `storageClassName` is immutable once bound. **Closed 2026-09-03** (WP-118 steps 3a/3b): discovered from the `is-default-class` annotation, injected into all five PVC-rendering applies, charts flipped to a deliberately invalid placeholder so a lost value fails loudly instead of binding to the wrong storage |
| B6 | Route53 `hostedZoneID: Z3HY376RT1N9S1`, `region: eu-west-3`, ACME contact email | `gitops/charts/cert-manager/values.yaml` | ACME DNS-01 cannot solve if `demo333` sits under a different parent DNS zone. **Closed 2026-09-03** (WP-118 step 3b): the three values moved to `ansible/confidential.yml` as `zuno_certmanager_route53_hosted_zone_id`/`_region`/`zuno_certmanager_email`, the re-apply was `changed=0`, and the chart defaults are now placeholders |
| B7 | Two identically-named tasks wrote `zuno/salesforce/technical` with competing key schemas: `url`/`access_token` (l.940, live) and `instance_url`/`token` (l.1001, inert because its variables were never documented) | `ansible/roles/vault/tasks/install.yml:1001-1014` | `vault kv put` replaces rather than merges, so only one schema can exist. Documenting the missing variables — the obvious fix — would have started the dead task and wiped the keys `mcp-salesforce` serves Comage from. **Closed 2026-09-02** (WP-118 step 4): `url`/`access_token` made the single canonical schema and the duplicate seed task deleted |
| B8 | All five `zuno_mariadb_backup_s3_{bucket,endpoint,region,access_key_id,secret_access_key}` are read but appear nowhere in `confidential.example.yml` | `ansible/roles/mariadb/tasks/install.yml:98-104`, `ansible/roles/vault/tasks/install.yml:1064-1076` | Undocumented prerequisite, and not merely cosmetic: with them unset `backups.s3.enabled` stays false, the ExternalSecret is never rendered, and **no MariaDB backup schedule exists at all**. **Closed 2026-09-02** (WP-118 step 4): all five documented in `confidential.example.yml` |
| B9 | Drifted RHOAI InstallPlan — the only `auto_fix: "manual only"` on the install path | `ansible/roles/openshift_ai/tasks/install.yml:90` | A cluster provisioned later than the pin gets a catalog publishing a newer CSV than `startingCSV`, and the install refuses to approve it. **Not a defect — the refusal is the reproducibility guarantee.** Closed as a decision, not a fix (2026-09-03): the gate stays, and the drift is now detected in `precheck.yml` from the PackageManifest, before the install runs |
| B10 | The four RHOAI dashboard feature flags (`disableKueue`, `disableTrustyAIEval` and siblings) were set by hand on the live cluster and had no applier at all | live `DataScienceCluster`/`OdhDashboardConfig` only — nothing in the repo | A fresh cluster comes up with the RHOAI dashboard missing the surfaces WP-115/WP-117 rely on, and no `make` verb restores them. **Closed 2026-09-03** by WP-123: the flags are reconciled from Ansible, drill-proven (check found the drift, reconcile fixed it, a re-run was a no-op, deleting a flag self-healed). Invisible to WP-118's audit by construction: a cluster-only mutation leaves nothing in the repo to grep for |
| B11 | `acme.enabled: true`, `certificatesIssuer: letsencrypt-route53` (production) and both `consumers.routerDefaultCert`/`apiServerNamedCert` shipped `true` — demo222's *end state*, committed to git | `gitops/apps/cert-manager/application-d1.yaml:36-49` | On the first sync of a fresh cluster ArgoCD patches `IngressController/default.spec.defaultCertificate` to `router-wildcard-tls`, a Secret that cannot exist yet, and adds an APIServer named certificate for the same absent Secret — breaking Console and route serving before any Certificate could be issued. The chart's own comment says these flip ONLY after `oc get certificate -A` shows Ready. Also skips the staging rehearsal ADR-0211 prescribes. **Closed 2026-09-04** (WP-132 step 3), live-verified — `changed=0`, values byte-identical, all 11 managed resources still present: the four values are now operator variables defaulting to the chart, which already ships the safe start of ADR-0211's rollout. Two guards added — one refusing consumers while ACME is off, one refusing to walk a live ACME track backwards, since rendering the chart at its defaults drops 11 documents to 3 and this Application prunes |
| B12 | Seven S3 buckets mix cross-cluster inputs and per-cluster outputs, and none is namespaced by cluster | `ansible/confidential.yml` plus `gitops/charts/*/values.yaml`, enumerated in ADR-0546 | A `demo333` installed today writes its RAG ingestion outputs, pgBackRest and MariaDB backups, RHOAI traces and MLflow artifacts into **`demo222`'s** buckets — the only blocker here that damages the *existing* cluster rather than the new one, and a direct violation of this ADR's own "`demo222` is left untouched" criterion. **Closed 2026-09-05** (WP-131): all eight components cut over to per-cluster `zuno-<cluster>-*` buckets, all six legacy shared buckets deleted, live-verified on `demo222`. `demo333`'s own five `zuno-demo333-*` buckets were created empty in eu-central-1 (region pivot, see Implementation notes) and re-populated entirely by `demo333`'s own pipelines during this run — nothing was copied from `demo222`. Isolation re-verified 2026-09-08 at ADR closure: separate regions (`demo222` eu-west-2, `demo333` eu-central-1), separate tags (`zuno.io/cluster`), no bucket policies, no replication, `BucketOwnerEnforced`/AES256 on both sets, `demo333`'s `confidential.yml` references only its own bucket names |
| B13 | The ACME DNS-01 identity was moved to `ansible/confidential.yml` and the chart flipped to placeholders, but `cert_manager` never loaded the file — so all three variables were always undefined and the `default()` chain resolved to the placeholders | `ansible/roles/cert_manager/tasks/install.yml` | Not a `demo333` blocker at all: a live `demo222` defect, armed and waiting. The next `make d0 install cert-manager` would have written `MYCLUSTERHOSTEDZONEID` / `mycluster-route53-region` / `acme-contact@mycluster.example.com` into `zuno-cert-manager-d1` and stopped DNS-01 from solving — and with B11's consumer flips on, a failed renewal eventually takes the router certificate with it. **Closed 2026-09-04** (WP-132): the loader added, and `check_confidential_var_loaders` in `check_docs.py` now fails any role that reads a documented variable without loading the file. Live-verified the same day — `make d0 install cert-manager` reported `changed=0` with both Applications byte-identical and no `mycluster` string, the whole ACME track still Ready |

B7 and B8 were closed by WP-118 step 4 on 2026-09-02, and both rows above were
rewritten that day. The audit had described B7 as a variable-name mismatch that
made the Salesforce seed "silently never run"; acting on it would have been
actively harmful. The seed does run — a *duplicate* task was dead, and the
enumerated fix (documenting its variables) would have made it run and clobber a
live consumer. B8's effect was understated: it is not only an undocumented
prerequisite, it is why this cluster has no MariaDB backup schedule. A static
audit reads intent, not behaviour; both corrections came from tracing the
consumers rather than re-reading the producer.

B9 was closed by WP-118 step 5 on 2026-09-03, and it is the one blocker whose
right answer was **not** to change the behaviour. `beta` is a moving channel —
it published `3.5.0-ea.2` when ADR-0002 pinned it, and `eus-3.5` already
carries the `3.5.0` GA — so a `demo333` provisioned later will legitimately be
offered a different build. Auto-approving whatever the catalog serves would
make the platform unreproducible, which is the thing this ADR exists to
establish; so the hard refusal in `install.yml` is kept exactly as it is, and
choosing a version stays a human decision.

What was wrong is only *when* the operator learns of it. The gate fired
mid-install, after the Subscription had landed, on a cluster already an hour
into Day 0. The PackageManifest carries the same fact, needs no Subscription,
and is readable as soon as the CatalogSource is ready — so `precheck.yml` now
compares the chart's pin against the channel head and records a finding naming
the exact value to set (the pin is read from the chart, not the live
Subscription, precisely because a fresh cluster has neither). Read-only and
never-failing, per precheck's contract. On `demo222` today it reports ALIGNED
and records nothing.

The residual manual step is therefore accepted and bounded: one deliberate
version choice, surfaced by a check instead of by a failure.

(Corrected 2026-09-04, WP-132.) This paragraph said `make d0 check`, and that
command rejects the component: `openshift-ai` is in `DAY1_RUN_COMPONENTS`, so
the probe runs under `make d1 check openshift-ai`. On a from-scratch run the
drift therefore surfaces after Day 0 completes and before the Day 1 openshift-ai
install — still hours earlier than the mid-install failure it replaces, but not
"before Day 0" as written. This is ADR-0344's defect class resurfacing in the
prose of the fix for it, and it was living in `discover_channel.yml`'s own
`fail` message too. WP-130's Day 0 readiness probe is the natural home if the
decision really should precede Day 0.

WP-132 also made the pin settable per cluster (`zuno_openshift_ai_version`), so
recording "this cluster runs a different build" no longer means editing a chart
default that every cluster renders from `main`. Pinning to a fixed channel such
as `eus-3.5` rather than a moving one is still the obvious follow-up if the
churn ever costs more than it buys.

B1, B5 and B6's mechanism were closed by WP-118 steps 2 and 3 on 2026-09-03, each in the
two-step order this constraint demands: apply live so the Application carries the
discovered value, verify the render is unchanged, only then flip the chart default. The
verification that mattered was not "the resources are unchanged" but "**ArgoCD has
actually rendered the placeholder chart** and the resources are still unchanged" —
checked with `git merge-base --is-ancestor` against each Application's synced revision,
because an unchanged resource proves nothing while the old chart is still what renders.

Three audit errors surfaced while executing it, all of them things a static read could
not have caught. The planned selector for B1 (`cluster-api-machine-role=worker`) matches
our own GPU MachineSets too, so the role would have bootstrapped from its own output. B5's
first inertia test passed while comparing two *empty* renders — three of the four charts
render no PVC until their Application's toggle is set. And an obvious-looking
`selectattr` on the dotted `is-default-class` annotation silently returns `[]`, which
would have failed all five installs on a cluster that has exactly one default class.

Audit pass 2 (2026-09-03) re-ran the same static search for cluster-identity
literals beyond B1–B9 and found none: the surviving `eu-west-2` occurrences are
the S3 *data-plane* region of `zuno-demo-rag-corpus`, which `mlops/values.yaml`
already comments as deliberately not the cluster's own region; the `ip-10-…`
node names appear only in comments; and every scheduling rule is expressed
against topology labels rather than node names.

That clean result is the finding, not a clearance. B10, B11 and B12 were all
found in the same pass, and none of them is a literal — B10 is a cluster-only
mutation that leaves nothing in the repo to grep for, B11 is a perfectly valid
end state committed to git, B12 is an architectural question about who owns a
bucket. Clause 5's bound held only for the class of defect a static read knows
how to see. This is why ADR-0547 replaces "remove the literals we can find"
with a rule that holds by construction: no chart default may carry a
cluster-specific value at all, and conformance is checked by the readiness
probe rather than by re-reading the tree.

B13 was found on 2026-09-04 while WP-132 was reading the same code for an
unrelated conversion, and it is the sharpest lesson on this page. WP-118 B6
followed the two-step order exactly — Application first, chart default second —
and still shipped a broken result, because the order was applied to the *value*
and not to the *surface*. Nothing loaded `confidential.yml` in that role, so the
new variables could never be defined; the `| default(chart)` fallback then
silently supplied whatever the chart held. While the chart still held the real
values that was invisible, and it is precisely what made the `changed=0`
inertia proof pass: the apply was inert for the wrong reason. Step two removed
the real values and left the fallback pointing at placeholders.

Two things follow. An inertia proof must state *why* nothing changed, not only
that nothing changed — the useful question is "what would this have looked like
if the mechanism were dead?", and B13's own re-verification passes it: the chart
defaults are placeholders now, so an absent loader would have rewritten the
Application, and it did not — `changed=0` is consistent with "the parameter works" and
with "the parameter is dead and the old value is still there". And the check
that prevents recurrence has to be mechanical: `check_confidential_var_loaders`
now fails any role reading a documented `confidential.yml` variable without
loading the file, which is ADR-0547 clause 6 applied to this defect class.

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

**Closed 2026-09-08.** `demo333` was provisioned, redeployed end to end via
`make day0/day1/day2 install` and `make d3 sign/backup/restore`, and passed
`make d0 check` / `make d1 check` / `make d2 check` / `make d3 check` /
`make d3 test all` (15/15) — matching, and on the Day 3 agent/platform gate
exceeding, `demo222`'s acceptance bar. `demo222` was left untouched
throughout (no `oc`/Vault/S3/Route53 mutation against it during the run;
re-verified at closure, see B12 above). No manual `kubectl`/`oc` patch was
left standing on `demo333` — every intervention below either landed as an
automation fix (commit referenced) or is an explicit, logged exception.

Below is every manual intervention, grouped by Jalon. Findings 1–36 happened
2026-09-06/07 provisioning and redeploying Day 0/Day 1; findings 37 onward
happened 2026-09-08 resuming after an overnight cluster stop, closing Day 2
and Day 3. All commits are on branch `demo333`, merged to `main` at the end
of this Jalon (Jalon 8).

**Jalon 3 — region pivot.** The cluster was first provisioned in
`eu-west-1`; the `g7e` GPU instance type this platform depends on does not
exist there (confirmed via `describe-instance-type-offerings`, zero
results), forcing a destroy-and-reprovision in `eu-central-1` (user
decision, infra provisioning is out of this ADR's scope). New
`zuno_machines_az_override` lets a cluster pin its GPU AZ without touching
the chart (`28198a45`, `c38430b8`) — `eu-central-1` offers `g7e` in AZs a/b
for this account, not a/c like `eu-west-2`. The five `zuno-demo333-*`
buckets, initially created in `eu-west-1`, were deleted (30 disposable
pgBackRest objects from the abandoned cluster) and recreated empty in
`eu-central-1`.

**Jalon 4 — Day 0, 15 findings (`94e95bf8`..`f277b6d1`):**
1. ArgoCD `openshift-gitops-limits` LimitRange (5Gi) below the
   application-controller's need (9Gi) blocked every sync — raised to 12Gi
   before the CR applies (`d6890833`).
2. `postgresql/check_s3_backup.yml` crashed on a virgin cluster (no
   `zuno-data` namespace yet) — namespace guard + "couldn't tell"
   semantics (`6d560b34`).
3. An Istio `DestinationRule` (Day 1 component) at ArgoCD sync-wave -31,
   one wave before `PostgresCluster` (-30), blocked postgresql-d1's entire
   sync on a virgin cluster — moved to wave 20, the chart's last
   (`0cdbfb95`).
4. No ArgoCD health check for `PostgresCluster` (PGO) — Argo declared it
   Healthy ~70s before Patroni elected a leader, so schema/monitoring-role
   Jobs ran into connection-refused — Lua health check added (`2da1ab8e`).
5. `confidential.yml`, copied from `confidential-demo222.back`, carried
   that cluster's *finished* ACME rollout state (consumers already
   flipped) — the router blocked on its first sync waiting for a
   nonexistent `router-wildcard-tls` Secret, circular lock with
   cert-manager-d1. Code guard: refuse the consumer flip until the
   Certificate is Ready (`b750ba97`); `confidential.yml` rolled back to
   the safe `acme_enabled`-only stage.
6. `realm-zuno.json`: three Keycloak group descriptions exceeded 255 chars
   (`GROUP_ATTRIBUTE.VALUE varchar(255)`), crash-looping the realm import
   — shortened (`d7379afa`). Unstuck the ArgoCD sync pinned to the old
   revision by patching the live `KeycloakRealmImport` CR content directly
   and deleting the stuck hook Job (a status-only patch does not work
   while a hook Job is still running — see
   [[argocd-failing-hook-pins-sync-revision]]).
7. AAP Controller's Demo Project delete returns 202 (async), not 204, on a
   fresh install — accepted both (`e09afa8d`).
8. A Day-check Role/RoleBinding in `kuadrant-system` (a Day 1 namespace)
   was applied by `aap-config` (Day 0), blocking its sync behind the
   sync-wave barrier — moved into the `connectivity-link` chart, gated on
   `project.enabled` (`3d940579`).
9. AAP's `tower.ansible.com` operator reconciles its CR queue with no
   inter-CR ordering — Job/Workflow Templates reconciled before their
   Project/Inventory existed, failed silently under `ignore_errors`
   (0/18 real JobTemplates, 8 zero-node workflow shells). The old
   annotation-nudge is dead (ansible-operator ignores metadata-only
   changes, proven live: 18 CRs annotated, 7 minutes, no effect) — fixed
   by deleting the CR so ArgoCD's selfHeal recreates it fresh
   (`d52e432a`).
10. AAP Gateway Route lookup had no retry, but the CR reports Healthy on
    ArgoCD immediately while the operator takes ~15-20 min — every host
    POST 403'd "License is missing" until the subscription attached.
    Fixed with a bounded wait (`e6f1f913`).
11. RHN subscription attach: the one-shot POST 400'd "Invalid
    subscription" with 8 available subscriptions on the account (worked
    at subscription #1 on `demo222`, never replayed since). Reproduced the
    real UI flow: list subscriptions, pick the largest valid one, PATCH
    settings, POST attach with `subscription_id` (not `pool_id`, which
    404s) — idempotent short-circuit if already valid+compliant
    (`e3d65aa4`).
12. `zuno-aap-installer` missing the `bind` verb on `clusterroles`
    (`system:image-builder`) — Kubernetes' escalation check refuses
    binding a permission the grantor doesn't hold (`f277b6d1`).
13. First-ever build under RHTAS-not-installed-yet loudly skips image
    signing (day1 build precedes day1 install on a fresh cluster) —
    catch-up is `make d3 sign all` (`9366b5df`), see Jalon 7.
14. The AAP Project tracked `main`, so every AAP-launched Job Template ran
    `main`'s code, not `demo333`'s fixes — `project.branch` injection +
    `scm_branch` convergence via the Controller API, live-verified
    (`bec66d5c`).
15. `gpu-c`'s MachineSet hit `InsufficientInstanceCapacity` for `g7e` in
    `eu-central-1b` — a transient AWS capacity shortage, not a defect;
    left retrying rather than moved to `eu-central-1a` (user decision).

**Jalon 5 — Day 1, 21 findings (`c904ae59`..`ffc36944`):**
16. First full Day 1 install under AAP 403'd on `clusterissuers`
    (service_mesh) — systematic diff of every Day 1/2/3 role's
    `api_version` against the `aap-installer` ClusterRole found 9 missing
    apiGroups, added at once (`c904ae59`).
17. `ansible/confidential.yml` is gitignored, absent in AAP's execution
    environment — every AAP job applied Applications at
    `targetRevision: main` regardless of finding 14's fix. New
    `ansible/branch-pin.yml`, committed (present in every checkout, local
    and AAP), loaded after `confidential.yml` (`4fcb5475`) — removed at
    this Jalon 8 merge, with the `confidential` pinning var.
18. Operator/operand webhook races across consecutive sync-waves (MariaDB
    Operator -32, MariaDB -30: "no endpoints available") — ArgoCD's
    auto-sync never retries a failed revision, wedging the app. Every
    Ansible-applied Application now carries `syncPolicy.retry` (5 tries,
    30s-5m backoff), same commit `4fcb5475`.
19. `istio-ca-root-cert` missing from `openshift-ingress` at Day 1 (a Day
    2 openshift_ai copy factored into a shared
    `ensure_istio_ca_in_openshift_ingress.yml`).
20. Kueue's `x-k8s.io` CRDs ship with the operand at sync-wave 20, but
    ArgoCD's dry-run validation kills the sync before any wave runs —
    `SkipDryRunOnMissingResource` on the 5 queue resources (`f4b283b7`);
    same deadlock and fix for openshift_ai's `OGXServer` (`87b74b75`).
21. `aap_launch`'s poller died on a single transient 503 (AAP's own
    Postgres failing over) — `failed_when: false` + explicit fail
    (`8f54df38`).
22. **`zuno-ogx` 80-minute crashloop**: the `zuno-postgres-exporter-metrics`
    NetworkPolicy only allowlisted `zuno-auth`/`zuno-aap` for direct
    primary:5432, not `redhat-ods-applications` (ogx/maas-db dial the
    primary directly, deliberately). The client-side TCP "succeeded" was a
    lying probe (Envoy) — proven with a raw SSLRequest byte after the fix
    (`ffc36944`). Invisible on `demo222`: its `ogx` predates the 5432
    Istio-exclusion flip.
23. RHOAI 3.5's DataScienceCluster phase is unreachable while our
    deliberate `OGXServer.overrideConfig` pins `ConfigGenerated: False`
    (an any-`False` health-check trap, see
    [[argocd-generic-health-check-any-false-condition-trap]]) — the
    install wait now accepts `Ready` OR
    `(ComponentsReady + DashboardReady + OGXReady) AND degraded ⊆ [ogx]`.
24. Tempo's validating webhook requires the requester to hold
    `tokenreviews create` — granted to `aap-installer`.
25. AAP's execution-environment `kubernetes.core` does not default to
    strategic-merge on built-ins (the local workstation's does) —
    `merge_type: strategic-merge` pinned explicitly on the core-bff patch;
    all 8 `state: patched` tasks in that role audited for the same gap.
26. A fresh RHOAI 3.5.0 install has no `dashboard-sa-token` volume at all
    (token auto-mounted, core-bff healthy unpatched) — the real signature
    of "needs the patch" is volume-present-but-mount-absent, not
    volume-absent; the patch guard corrected accordingly.
27. The check-side mirrors of findings 23 and 26 (`precheck.yml`) had the
    same two defects independently — every install-side fix needs the
    identical check in `precheck`/`diagnose`.
28. Under the `aap-day0-check` ServiceAccount, `k8s_info` on a forbidden
    Secret raises (403) instead of returning empty — diagnose aborted;
    `failed_when: false` + `'resources' in item` guard + a Role scoped to
    `get` on `maas-db-config` alone.
29. Missing brace in a hand-edited `combine(syncPolicy.retry, ...)` —
    caught by executing, not just reading (recurring lesson).
30. 6 RHOAI dashboard UI modules stuck `Init:1/2` ~2h: vendor egress
    NetworkPolicies dropped the sidecar's xDS dial to istiod — additive
    NetworkPolicy, gated `dashboardModulesMeshEgress` (`bb749061`).
31. A hand-edited-looking Jinja bug (`default 'x'` missing parens) in
    `auto.yml`, corrected.

**JALON 4 CLOSED 2026-09-06 ~22h05, JALON 5 CLOSED 2026-09-07 ~16h15** —
`make day0 install` / `make d0 check` and `make day1 install` /
`make d1 check` both rc=0 from scratch, 36 findings total, all
committed/pushed. Cluster was stopped overnight by the user
(`sxcm`) between Jalon 5's finish and Jalon 6's start; resumed cleanly per
[[post-restart-recovery-checklist]] (no Vault re-seal issue this time,
ArgoCD had no wedged operations).

**Jalon 6 — Day 2, `make day2 install` / `make d2 check`, 8 findings, all
first-real-run-under-AAP RBAC/NetworkPolicy/wiring gaps closed 2026-09-08:**
32. `trustyai-eval`'s image was never built (`ansible_role
    trustyai_eval_build`, part of `day1_build.yml`, had genuinely never
    run) — `make d1 build trustyai-eval`.
33. RAG ingestion had never produced a row: the KFP recurring runs (day2
    install) auto-fired 4 domains on cluster restart and raced
    `embeddings-predictor`'s cold start — `stage_validate` correctly
    failed without advancing `manifest.json`; re-triggered the same 4 runs
    once the model was Ready, 2276 real rows landed in `rag-tech`.
34. `maas-api` (RHOAI ModelsAsService, namespace `redhat-ai-gateway-infra`)
    CrashLoopBackOff on the Postgres primary — that namespace was missing
    from `zuno-postgres-exporter-metrics`'s direct-to-primary allowlist
    (`39dfad8c`).
35. `rhtas_config` (WP-111/ADR-0535: policy-controller-operator,
    ClusterImagePolicy, TrustRoot, the `zuno-signer-client-secret` mirror)
    was written but **never invoked by any playbook or the Makefile** —
    wired into `day1_install.yml` (`73147241`), then three further live
    bugs in its own first-ever run: OLM's OwnNamespace lands the operator
    in `policy-controller-operator`, not `zuno-rhtas` (`688ff826`);
    `aap-installer`'s deliberately read-only CRD grant needed a narrow
    `patch` scoped to exactly `clusterimagepolicies.policy.sigstore.dev`
    (`f9474d03`, same escalation-safe pattern as the `clusterroles/bind`
    grant); the API server couldn't reach its admission webhooks —
    `allowApiServerWebhooks: true` added to its `platformNamespaces` entry
    (`adb4bd72`), plus a defensive TUF-reachability allow (`247703bd`).
36. Once `zuno-signer-client-secret` existed, the 14 images built before
    it did (agent-frontend/bff/runtime, ai-gateway, aiagent-operator,
    diagram-render, mcp-{aap,confluence,gateway,git-forge,salesforce},
    mlops, rag-ingestion, rag-service) had never actually been signed
    (build-time signing loudly skips when RHTAS isn't ready, finding 13) —
    rebuilding the 7 owning components re-signed all 14, confirmed live
    per image.

**Jalon 7 — Day 3, `make d3 check` / `test all` / `sign` / `backup` /
`restore`, all green 2026-09-08:**
37. `d3 check` first run reported **MLflow not installed** — `mlflow` is a
    Day 2 component whose Application had simply never been applied
    (`d2 check`'s "successful" workflow status never surfaces a
    component's "NOT installed" report line). `make d2 install mlflow` —
    no defect, just never run.
38. `d3 test all`: 15/15 passed, first try.
39. `make d3 backup postgresql` 403'd — `postgres-operator.crunchydata.com`
    was never granted to `aap-installer` (postgresql moved to Day 0 by
    ADR-0421, never exercised this path under AAP). Scoped
    `get/list/watch/patch` on `postgresclusters`, no create/delete
    (`5e80f018`).
40. `make d3 restore postgresql` failed three times, none of them RBAC —
    `resolve_backup_s3_creds.yml` reads `ansible/confidential.yml`
    directly, which does not exist inside AAP's execution environment
    (fresh git checkout); added an in-cluster fallback reading
    bucket/endpoint/region from the live `PostgresCluster`'s own spec and
    the access/secret keys from `zuno-postgresql-backup-s3` — first
    attempt wrongly assumed that Secret had separate data keys (it holds
    one `s3.conf` ini blob, `464f8348` → `1bf72627` fixed the parsing);
    second attempt left `repo2-path` unset, defaulting to the wrong value
    and making the check "successfully" query an empty S3 prefix
    (`caa1f357`, resolved from `spec.backups.pgbackrest.global`). Third
    attempt succeeded: PostgresCluster restored from repo2, 3/3 instances
    rolled out, `rag.document_embeddings` verified intact post-restore
    (2276 rows, unchanged).

**Total: 40 logged manual interventions across the full redeploy, every one
either fixed in automation (commit referenced above) or an explicit,
bounded exception (findings 9's AWS capacity wait, B9's version-pin
decision).** S3 isolation between `demo222` and `demo333` verified clean at
this ADR's closure (separate regions/tags/no cross-policy, see B12).

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
- [ADR-0546](0546-introduce-a-cross-cluster-source-bucket-and-per-cluster-s3-bucket-convention.md)
- [ADR-0547](0547-parameterize-every-cluster-specific-value-in-ansible.md)
