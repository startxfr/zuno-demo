# WP-099: Fix three live defects found running `make d0 install aap-config` for real

- **State:** Done - `make d0 install aap-config` ran clean end to end
  2026-08-30 (`failed=0`, `changed=0` on the second consecutive run), all
  14 Job Templates/7 Workflow Templates/2 credentials confirmed live via
  the Controller API.
- **ADRs:** ADR-0418 (clauses 4/6 - Job/Workflow Template registration).
- **Depends on:** WP-094 (Job Templates), WP-095 (Workflow Templates),
  WP-098 (Demo-object cleanup - ran in the same investigation).
- **Unblocks:** the pending live verification follow-up from WP-094/095/097.
- **Estimated files touched:** 3 (`gitops/charts/aap/values.yaml`,
  `gitops/charts/aap-config/templates/workflowtemplate.yaml`,
  `ansible/roles/aap_config/tasks/install.yml`).

> Execute this brief as a standalone task from the repository root.

## Goal

The first real `make d0 install aap-config` run (registering 21
`tower.ansible.com` CRs at once - WP-094/095's 14 Job Templates + 7
Workflow Templates, on top of the pre-existing `zuno-day0-check`/
`zuno-cluster-reader` pair) surfaced three independent live defects that
no amount of offline `--syntax-check`/`bash -n` could have caught. This
WP fixes all three.

## ADR references

ADR-0418 clauses 4 (Job Template registration) and 6 (Workflow Template
registration) - hygiene/correctness fixes to already-decided scope, not
new clauses.

## Preconditions (verify before starting)

- WP-094/095/097/098 merged.
- A live AAP instance with `zuno-day0-check` already registered (WP-073) -
  needed to reproduce/diagnose the resource-operator load defect, which
  only manifests once 20+ CRs are registered simultaneously.

## Repo changes (step by step)

### 1. `resource-operator-controller-manager` crash loop (resource starvation)

Registering 21 CRs at once spawns ~21 concurrent ansible-runner
reconciliation subprocesses inside the operator's single controller-manager
pod. Confirmed live: pegged at 999m/1000m CPU and 2036Mi/2048Mi memory,
failing its own `/healthz` probe (1s timeout) and getting killed by
kubelet - 28 restarts in ~30 minutes, nothing ever finished reconciling.
Sibling operators in the same CSV (`aap-operator.v2.7.0-...`) already run
at 2 CPU/4000Mi; `resource-operator` alone shipped at 1 CPU/2Gi.

- **Immediate unblock (live, not durable alone)**: `oc patch deployment
  resource-operator-controller-manager -n zuno-aap` raising
  requests/limits to `200m/512Mi` / `2 CPU/4Gi`. Confirmed live: 0
  restarts afterward, full 21-CR backlog reconciled within ~90 seconds.
- **Durable fix**: `gitops/charts/aap/values.yaml`'s
  `operator.subscription.operator.config.resources` - the vendored
  `startx/operator` chart's `templates/subscription.yaml` already
  supports `spec.config.resources` on the rendered OLM `Subscription`
  (confirmed by pulling the chart locally: `helm pull startx/operator
  --version 21.3.277 --untar`). OLM applies this uniformly to **every**
  container in **every** Deployment the CSV installs - there is no
  per-Deployment targeting in the OLM API - so the chosen values
  (`200m/512Mi` requests, `2 CPU/4Gi` limits) are a floor high enough for
  `resource-operator`'s real need, accepted as a harmless
  over-provisioning of the already-larger sibling deployments (4000Mi ->
  4Gi is negligible) rather than leaving a defect OLM has no mechanism to
  fix surgically.

### 2. Workflow Template nodes never resolved (`organization` FK)

Every one of the 7 Workflow Templates failed identically:
`Unable to Find unified_job_template: {'type': 'job_template',
'organization': 69}` (0 matches, every time). Root cause chain, confirmed
live:

- `job_template.organization` is `null` for **every** Job Template on
  this Controller - JobTemplate has no `organization` field of its own
  (CRD or API), it is only ever a read-through of its Project's
  organization.
- The `zuno-demo` Project's own `organization` is *also* `null`, despite
  its CR's `spec.organization: zuno` - and can never be fixed after the
  fact: `PATCH .../projects/7/ {"organization": 69}` is rejected outright
  with `"Organization cannot be changed when in use by job templates."`
- Deeper still: the operator's own `project` role
  (`/opt/ansible/roles/project/tasks/main.yml`, read directly from the
  running resource-operator pod) unconditionally `end_play`s the instant
  `status.isFinished` is true, forever - there is no mechanism, CRD field,
  or annotation that makes it re-run once finished. Whatever caused the
  organization to land null on this Project's first-ever reconcile
  (2026-08-25, before WP-094/095 existed) can never self-heal.
- Fix: `gitops/charts/aap-config/templates/workflowtemplate.yaml` no
  longer sets `unified_job_template.organization` on any node. Read
  directly from the operator's `ansible.controller.workflow_job_template`
  module source: the `organization` filter on its `unified_job_templates`
  lookup is only added when the node explicitly supplies one - omitting
  it falls back to a plain name+type match, which is exactly as
  unambiguous here (every Job Template name in this repo is already
  globally unique) and doesn't depend on any Project ever having a
  resolvable organization.

### 3. `zuno-day3-sign` Job Template creation: "Playbook not found for project."

`day3_sign.yml` was added to the repo on 2026-08-28; the `zuno-demo`
Project's SCM checkout was last synced 2026-08-25 and, per the same
"`isFinished` sticky forever" defect above, will **never** re-sync on its
own - no CR change, annotation patch, or force-reconcile touches it once
`status.isFinished` is true. Any future playbook addition would hit the
exact same failure.

- Fix: new tasks in `ansible/roles/aap_config/tasks/install.yml`, right
  after the Project is confirmed to exist and before any Job Template
  wait - `POST .../projects/{id}/update/` (bypassing the stuck CR
  entirely, straight through the Controller API) and poll
  `/project_updates/{id}/` until terminal, failing loudly if the sync
  itself didn't succeed. Runs unconditionally on every install (~15s,
  idempotent) rather than only when a nudge is already known to be
  needed, since the whole point is to catch a drift the existing
  count-based nudge logic cannot see.

### 4. Project SCM re-sync task itself: wrong expected HTTP status

The new task from fix #3 above was written expecting `status_code: 201`
on `POST projects/{id}/update/`, based on a manual `curl` test during
diagnosis that only checked the JSON body, never the actual HTTP status.
Running it for real via `make d0 install aap-config` failed immediately:
the Controller API returns **202** (Accepted, async job queued), not 201.
Fixed in the same task (`ansible/roles/aap_config/tasks/install.yml`).

### 5. `zuno-day3-sign`'s stuck CR needed a real delete, not a nudge

Even after fix #3/#4 landed and the Project's SCM checkout was
genuinely current, `zuno-day3-sign` alone still didn't get created - the
"force the tower.ansible.com CRs to reconcile" annotation-only patch
this repo uses everywhere else never re-triggers this operator's
watch for a `JobTemplate` whose `metadata.generation` hasn't changed
(confirmed live: `generation: 1`, unchanged, and zero fresh reconcile
attempts in the operator's own logs after the annotation patch - this
operator's ansible-operator watch only reacts to genuine spec changes,
not metadata/annotation-only updates or its own status writes). Since
the `JobTemplate` CRD has no `state: absent` field to express a
declarative delete, and the CR has zero dependents (it didn't exist on
the Controller yet), the fix was operational, not code: delete the CR
(`oc delete jobtemplate.tower.ansible.com zuno-day3-sign -n zuno-aap`),
ArgoCD's `selfHeal` recreated it within seconds, and the fresh CR
reconciled cleanly on its first attempt. This is a defect-class note,
not a repo change: the existing annotation-nudge mechanism used
throughout `install.yml` is silently ineffective for any CR whose
watch predicate is generation-based and which needs a *retry* of an
already-attempted (and already-`ignore_errors`-swallowed) failure -
worth remembering if another Job/Workflow Template ever gets stuck the
same way.

## What NOT to touch

- The `zuno-demo` Project's `spec.organization` field in
  `ansibleproject.yaml` - correct as declared; the Controller-side value
  being stuck null is a pre-existing operator defect from before this WP,
  not something this repo's CR spec caused or can fix by editing it
  further.
- `zuno-cluster-reader`/`zuno-aap-installer` credentials, the 13 Job
  Templates that already exist and already work - none of the three
  fixes above touch credential attachment, Survey wiring, or any
  already-working Job Template.
- Any attempt to delete/recreate the `zuno-demo` AnsibleProject CR to fix
  its organization "properly" - rejected as too risky for this pass (13
  live Job Templates already reference it by name; a delete+recreate
  window risks a real outage for zero functional gain now that the
  Workflow Template fix above no longer depends on the organization being
  set at all).

## Acceptance checks

- `ansible-playbook --syntax-check ansible/playbooks/day0_install.yml`
  passes.
- `helm template` on `gitops/charts/aap-config` (with `aapConfig.enabled:
  true`) renders every Workflow Template without an `organization` key
  under any node's `unified_job_template`.
- `python3 platform/docs/check_docs.py` passes.
- Live (confirmed 2026-08-30): after the resource-operator resize,
  `oc get pods -n zuno-aap | grep resource-operator` shows `1/1 Running`
  with 0 new restarts; all 13 pre-existing-plus-new Job Templates and all
  7 Workflow Templates report `isFinished: true` with no error; a direct
  Controller API query (`GET .../workflow_job_templates/`) lists all 7 by
  name.
- Live, confirmed 2026-08-30: two consecutive `make d0 install
  aap-config` runs (second run `failed=0, changed=0`, fully idempotent)
  registered all 14 Job Templates including `zuno-day3-sign` (after the
  one-time CR delete+recreate from fix #5), all 7 Workflow Templates with
  full node sets, both credentials, and Keycloak SSO - `GET
  .../job_templates/` and `.../workflow_job_templates/` both confirm the
  complete set by name.

## Operator / human follow-up

- Confirm the durable `Subscription.spec.config.resources` change
  actually reaches the 7 CSV-owned Deployments once ArgoCD syncs it -
  **done**, confirmed live: `oc get subscription
  ansible-automation-platform-operator -o jsonpath='{.spec.config}'` and
  the running `resource-operator-controller-manager` Deployment's own
  `resources` block both show the new values, OLM picked it up with no
  CSV version bump.
- Launch `zuno-day1-check-workflow` for real and confirm in the
  Controller UI that its parallel waves (kiali/grafana; lws/jobset/kueue)
  actually start concurrently - WP-095's own still-open acceptance item,
  now finally unblocked (structurally ready; wave-timing itself not yet
  observed from a real launch).

## Status updates

- 2026-08-30: All three original defects plus two more found running the
  fix itself (##4 wrong HTTP status code, #5 the stuck CR needing a real
  delete) diagnosed and fixed; two consecutive `make d0 install
  aap-config` runs confirm a fully clean, idempotent pass with all 14 Job
  Templates/7 Workflow Templates/2 credentials live. State: `Done`.

## Rollback

`git revert` for the two chart/task changes. The resource-operator resize
has no revert path that restores prior (broken) behavior - reverting the
`Subscription.spec.config.resources` change stops applying the durable
override but doesn't affect the already-recreated pod's runtime resources
directly (the pod is running fine at the new, larger size regardless of
where the value is declared).

## Out of scope / deferred

- The `zuno-demo` Project's stuck `organization: null` itself - not fixed
  (see "What NOT to touch"); the Workflow Template fix works around it
  rather than resolving the underlying Project state.
- A general mitigation for the operator's "`isFinished` sticky forever"
  defect on any *other* `AnsibleProject`-shaped resource this repo might
  add later - flagged here as a defect class worth remembering, not
  generalized into a reusable task in this pass.
