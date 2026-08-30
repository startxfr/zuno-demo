# WP-099: Fix three live defects found running `make d0 install aap-config` for real

- **State:** Repo work merged - live re-verification pending on the fixed
  paths (resource-operator sizing and the Workflow Template organization
  omission were confirmed fixed live 2026-08-30; the SCM re-sync task is
  new code, not yet exercised end to end via `make d0 install aap-config`
  itself).
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
- Live, still pending (needs a fresh `make d0 install aap-config` run
  exercising the new SCM re-sync task and the durable Subscription
  resize together): `zuno-day3-sign` appears in
  `GET .../job_templates/` after a clean run with no manual API
  intervention.

## Operator / human follow-up

- Run `make d0 install aap-config` again end to end and confirm it
  completes with no manual API calls needed this time (the SCM re-sync
  task and the durable resource sizing are both new code, exercised
  individually live but not yet together through the Makefile path).
- Confirm the durable `Subscription.spec.config.resources` change
  actually reaches the 7 CSV-owned Deployments once ArgoCD syncs it (OLM
  is expected to pick up a `Subscription.spec.config` change without a
  CSV version bump - re-verify this cluster does the same, since the
  live patch already fixed the symptom independently and could mask a
  durable-fix regression).
- Launch `zuno-day1-check-workflow` for real and confirm in the
  Controller UI that its parallel waves (kiali/grafana; lws/jobset/kueue)
  actually start concurrently - WP-095's own still-open acceptance item,
  now finally unblocked.

## Status updates

- 2026-08-30: All three defects diagnosed and fixed live during a real
  `make d0 install aap-config` run; repo changes merged. Resource-operator
  and Workflow Template fixes confirmed live; SCM re-sync task added but
  not yet exercised via the Makefile path (the live "Playbook not found"
  was fixed by a one-off manual `project/7/update/` API call during
  diagnosis, before the code fix existed). State: `Repo work merged - live
  re-verification pending`.

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
