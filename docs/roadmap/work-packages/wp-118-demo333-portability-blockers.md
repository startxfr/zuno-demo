# WP-118: Close the demo333 portability blockers recorded in ADR-0517

- **State:** Not started (2026-09-02) — the nine blockers are enumerated in ADR-0517's
  *Known blockers* section from a static audit; none is fixed. No `demo333` cluster
  exists, so this WP is entirely repo-side and can land before one is provisioned.
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

### Step 1 — domain literals (B2, B3, B4)

Five charts bypass the token because they use a differently-named key or embed the
domain mid-string: `grafana/values.yaml:74`, `kiali/values.yaml:60`,
`tempo/values.yaml:62` (all `appsDomain`, never substituted), `mlops/values.yaml:135-136`
(full `keycloakUrl`/`frontendUrl`), `connectivity-link/values.yaml:61` (`demoHostname`).

Two call sites need the value re-supplied in the role rather than the manifest, because
their `gitops_app_extra_helm_values` replaces the block wholesale: `connectivity_link`'s
d1 apply, and `grafana`, which applies d1 **twice** — factor a shared base-values fact,
as `lightspeed_config/tasks/install.yml:99` already does.

Also rewrite the comments in `grafana/values.yaml:70-73` and `tempo/values.yaml:59-61`:
they currently advertise the anti-pattern this step removes.

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

### Step 4 — undocumented prerequisites (B7, B8)

`ansible/roles/vault/tasks/install.yml:998-1003` reads `zuno_salesforce_instance_url` /
`zuno_salesforce_token` while `confidential.example.yml:81-82` supplies
`zuno_salesforce_url` / `zuno_salesforce_access_token`, so the
`zuno/salesforce/technical` seed silently never runs — the `!= 'xxxxxx'` guard sees an
undefined variable and skips without error. And `install.yml:1061-1065` reads MariaDB
backup S3 keys that appear nowhere in the example file. Both are pure documentation and
naming fixes, and both affect `demo222` today, not only a future `demo333`.

### Step 5 — RHOAI InstallPlan drift (B9)

`ansible/roles/openshift_ai/tasks/install.yml:90` is the only `auto_fix: "manual only"`
on the install path. A new cluster's catalog will publish a newer CSV than the pinned
`startingCSV`, and reconcile refuses to approve drifted InstallPlans. This is the most
likely blocker of an actual `demo333` run and probably cannot be fully automated — the
deliverable is a documented decision, not necessarily code.

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
