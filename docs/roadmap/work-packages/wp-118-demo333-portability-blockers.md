# WP-118: Close the demo333 portability blockers recorded in ADR-0517

- **State:** Repo work merged (steps 1, 4 and 5 of 5, 2026-09-03 — B2/B3/B4, B7/B8 and
  B9 closed; steps 2 and 3 in progress). No chart default names `demo222` any more.
  Step 4 corrected ADR-0517's own B7 row, which described the defect wrongly in a way
  that would have caused an outage if acted on; step 5 closed B9 as a decision to keep
  the InstallPlan gate and detect the drift earlier, not as a behaviour change. No
  `demo333` cluster exists; every remaining step is repo-side and can land before one is
  provisioned.
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

### Step 2 — AWS infra identity (B1)

`gitops/charts/machines/values.yaml` hardcodes `cluster.id: demo222-kpkqk`, the security
group, three subnet names, a pinned AMI and the region. This one cannot use token
substitution: `machineSet.list` is a list (Helm replaces lists wholesale) and Helm cannot
template a dependency subchart's `values.yaml`. It must come from the role via
`gitops_app_extra_helm_values`, derived at run time from an installer-created worker
MachineSet in `openshift-machine-api` (select on
`machine.openshift.io/cluster-api-machine-role=worker`, **rejecting** anything carrying
`machine.startx.io/group` so the role never bootstraps from its own output).

The dict must re-state the `cluster-machine.{cluster.autoscaler,machineSet,machineAutoscaler}.enabled`
toggles from `application-d0.yaml`, or `machineSet.enabled` falls back to false and
ArgoCD prunes all three GPU MachineSets. **This is the most dangerous edit in the WP.**

### Step 3 — StorageClass and DNS (B5, B6)

Four `gp3-csi` defaults (`models:296`, `postgresql:71`, `mariadb:105`, `grafana:85`) and
cert-manager's Route53 `hostedZoneID`/`region`/ACME email. The storage classes get a
shared `resolve_cluster_default_storage_class.yml` discovery task feeding the four roles'
existing `gitops_app_extra_helm_values` — including **both** blocks in postgresql's
`restore.yml`, or the restore path silently reverts it. The Route53 facts are operator
configuration and belong in `ansible/confidential.yml`.

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
