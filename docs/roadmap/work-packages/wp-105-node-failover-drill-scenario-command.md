# WP-105: `make d3 scenario-failover-node` - live GPU-node failover drill (qwen-normal ↔ qwen-wesh)

- **State:** Done (2026-08-30 — Part A merged and live-verified
  end to end on the real cluster, via the actual `make d3 scenario-failover-node`
  command (interactive TTY, real human confirmation pause): baseline probe,
  cordon+kill, `Pending` confirmation, failover probe, uncordon+reschedule,
  restore probe all passed for both Comage
  (`local-wesh(-maas)` → `local-qwen35(-maas)` → `local-wesh(-maas)`) and
  Tekos (`ovhcloud-gpt-oss-120b` unchanged throughout, the decoupling
  control) — full verdict JSON in
  `docs/roadmap/evidence/adr-0536-node-failover-drill.md`. Independently
  corroborated by the operator manually driving the real chat UI for both
  agents during the live outage window: Tekos showed no disruption; Comage
  was slow/intermittently erroring for a period after the cordon+kill, then
  correct via the fallback, with the same brief pattern again after restore
  - matching the automated probes' own "timed out" verdict during the exact
  cutover window (that check is warn-only by design, not a hard failure, for
  precisely this reason). Three real bugs found and fixed live during Part
  A (see the evidence doc): a restore-playbook crash reading `spec.nodeName`
  off a genuinely unschedulable `Pending` pod, a too-tight 30s probe HTTP
  timeout that didn't account for a freshly-rescheduled model's cold-start
  first response, and a restore-playbook idempotency gap that made a re-run
  after a partial success fail needlessly. 2026-08-31 — Part B repo work
  merged and its CRs/RBAC live-verified against the real Controller (ArgoCD
  sync of `zuno-aap-config-d1` + `make d0 install aap-config`): the
  `zuno-day3-scenario-failover-node-workflow`'s 3 nodes (`inject` job,
  `approve-restore` approval, `restore` job) confirmed to exist correctly
  via the Controller API, and `aap-ops-team` confirmed to hold both execute
  and the new approve role on it (`aap-reader-team` view-only, as designed).
  Two more real bugs found and fixed live during this verification (see the
  evidence doc): the chart's unconditional `extra_data.target_component`
  broke node creation on these `ask_variables_on_launch: false` Job
  Templates (silently, via `ignore_errors` - the CR still said `Successful`
  with zero actual nodes), and approving an approval node needs a genuinely
  separate `awx.approve_workflowjobtemplate` permission which itself needed
  `view_workflowjobtemplate` bundled in to be accepted by Controller's own
  role_definition validation - both confirmed live and fixed. 2026-08-31 —
  **Part B live-verified end to end, real run:** launched
  `zuno-day3-scenario-failover-node-workflow` for real (workflow job 579).
  First attempt (job 576) hit a third real bug - `zuno-aap-installer` had
  zero node access at all, `oc adm cordon` 403'd - fixed by a narrow
  `get`/`list`/`watch`/`patch`-on-`nodes` amendment to its ClusterRole (no
  create/delete, no Machine/MachineSet access). Second attempt (job 579)
  succeeded completely: baseline probe, cordon+kill, failover probe (same
  expected "timed out" warn-only miss as Part A's own authoritative run),
  a real human Approve click in the Controller UI, then uncordon+reschedule
  +restore probe - Comage `local-wesh-maas` → `local-qwen35-maas` →
  `local-wesh-maas`, Tekos `ovhcloud-gpt-oss-120b` unchanged throughout,
  overall workflow `status: successful`. Full trace in the evidence doc.
  **WP-105 is closed - both Part A and Part B are live-verified end to end.**)
- **ADRs:** ADR-0536 (Implemented), ADR-0418 (Implemented - `aap_route`/Workflow Template mechanism this WP extends).
- **Depends on:** WP-094 (Job Templates), WP-095 (Workflow Templates), WP-097 (make/AAP routing), WP-103 (launch-RBAC), WP-087/ADR-0526 (the qwen-normal/qwen-wesh fallback this drill proves).
- **Estimated files touched:** ~10 (2 new ADR/WP docs + 1 evidence doc, 1 new Python probe script, 2 new Ansible playbooks, Makefile, check_docs.py, roadmap tracker; Part B additionally touches the aap-config chart/role).

> Execute this brief as a standalone task from the repository root.

## Goal

Prove, live, that Comage actually fails over from `local-wesh` to
`local-qwen35` when the wesh model becomes physically unschedulable (node
cordoned, pod killed) - not just when a dependency like MaaS goes unreachable
(already drilled, ADR-0521) - while Tekos's chat traffic (routed off-cluster
to `ovhcloud-gpt-oss-120b`) is unaffected throughout, as a decoupling
control. Package the drill as a standing `make d3 scenario-failover-node`
command, built local-first then transposed to a full AAP Workflow Template
with a human approval gate, per this repo's own "every new make action gets
both a local and an AAP path" convention (ADR-0418 clause 6).

**Revision, 2026-08-30 (before first live run):** originally scoped the
other direction (kill `qwen3.5-9b`, prove Tekos fails over to `local-wesh`).
Live investigation found that's unprovable through real chat traffic - see
ADR-0536's Context section for the full finding (Tekos's only chat-reachable
task is a reflexional one routed to OVH first, never touching `local-qwen35`
or `local-wesh` at all). Comage's own primary task, `check-deal-status`, is
chat-reachable, non-reflexional, and already leads `local-wesh(-maas)` then
`local-qwen35(-maas)` - so this WP now drills that direction instead, which
was previously listed below as "out of scope" future work before this
finding made it the only viable one.

## Why

ADR-0526's Status line records this fallback path as explicitly untested
("STILL NOT TRUE"). ADR-0526's own Consequences section already names the
risk: two permanent MIG nodes, five model workloads, `"losing a node now
leaves at least two models unschedulable until capacity returns"`. Nobody has
ever forced that condition and watched what the calling agents actually get
back.

## ADR references

ADR-0536, Decision 1-5 and Consequences. Read that ADR first - it has the
full rationale for each design choice below (dynamic node discovery,
PromQL-based proof instead of log-reading, the semantic-cache precondition
check, the two-playbook split).

## Preconditions (verify before starting)

- `oc get pods -n zuno-ai-run -l app.kubernetes.io/name=qwen35-9b,kserve.io/component=workload -o wide`
  shows exactly one `Running` pod, and the same with `qwen35-9b-wesh` shows
  exactly one `Running` pod, each on a different node - confirms the
  topology ADR-0536 assumes still holds before touching anything live. The
  `kserve.io/component=workload` half of the selector is required - the
  bare `app.kubernetes.io/name` label also matches the unrelated
  `*-router-scheduler` pod on a different node entirely (live-caught
  2026-08-30 by the inject playbook's own precondition check correctly
  refusing to proceed on "found 2" - see `day3_scenario_failover_node_inject.yml`'s
  `scenario_failover_model_label` fact).

  **Found false live 2026-08-30, before this drill's first run:** both pods
  were colocated on `ip-10-18-15-25` (WP-092/ADR-0414's anti-affinity was
  only `preferred`, and both pods had been recreated in the same ~40s
  window during a routine restart - satisfiable elsewhere, but scoring
  still chose to violate it). Fixed live via a 3-pod shuffle (temporarily
  scaling `qwen36-27b-instruct-kserve` to 0 to break a scheduling race,
  full sequence not reproduced here - see the session transcript) that
  restored the originally-intended placement (`qwen3.5-9b` +
  `qwen36-27b-instruct` on `ip-10-18-15-25`; `qwen3.5-9b-wesh` +
  `gpt-oss-20b` on `ip-10-18-67-65`), and by promoting this pair's
  anti-affinity to `required` in `gitops/charts/models/templates/llminferenceservice-qwen35.yaml`
  / `llminferenceservice-wesh.yaml` (Amendment to ADR-0526 decision 5, see
  ADR-0536 Decision 6) so it cannot silently drift back. Re-run this precondition
  check before every future live use of this drill regardless - a `required`
  term guarantees separation going forward, but does not retroactively
  guarantee today's placement stays correct if the chart is ever reverted.

  **Live-verified fixed, 2026-08-30**, after pushing the chart change and
  syncing `zuno-models-d1` (ArgoCD app, `gitops/charts/models` path):
  `qwen35-9b-kserve-7b4968bcd9-d9x9b` `2/2 Running` on `ip-10-18-15-25`,
  `qwen35-9b-wesh-kserve-689595d44f-jt9kv` `2/2 Running` on `ip-10-18-67-65`,
  both pods' live `spec.affinity` confirmed carrying the new
  `requiredDuringSchedulingIgnoredDuringExecution` term against each other.

  **New operational finding, worth remembering for any future change to
  these 5 models' pod templates:** both `qwen35-9b-kserve` and
  `qwen35-9b-wesh-kserve` Deployments use the default `RollingUpdate`
  strategy (`maxSurge: 25%`, `maxUnavailable: 25%` → 1/0 at replicas=1).
  With `zuno-ai-run-gpu-cap` permanently saturated (3/3 `mig-1g.24gb`, 2/2
  `mig-2g.48gb` at steady state), a surge pod is unconditionally rejected
  at admission (`exceeded quota: zuno-ai-run-gpu-cap`) - the rollout
  deadlocks forever with the old pod still `Running` (harmless, but the new
  pod template never takes effect) until an operator manually scales the
  OLD ReplicaSet to 0 to free the slot, then nudges the new ReplicaSet
  (scale 0→1) past its exponential backoff. This will recur on every future
  pod-template change to any of these 5 GPU-saturated models unless the
  chart is changed to `strategy: {type: Recreate}` - out of scope for this
  WP, flagged here rather than fixed silently.
- `platform/ai-gateway/provider-routing.yaml` has no `cache_enabled: true`
  entry for `local-qwen35(-maas)`/`local-wesh(-maas)` (grep for it) - if this
  has changed, stop and re-read ADR-0536's Decision 5 before proceeding.
- Confirm with any other session known to be operating on this shared
  cluster before running the live drill (A.5 below) - standing rule since
  the WP-084 collision, still in force.

## Repo changes

### Part A - local version (build and validate this first)

**A. `evaluations/scenario_failover_probe.py` + `evaluations/scenario_failover_verify.py`**
(both new, landed). agent-runtime/ai-gateway have no external Route (only
in-cluster Service DNS - same reasoning
`ansible/roles/agents/tasks/run_acceptance_gate.yml`'s own header comment
gives for why every live chat probe in this repo already runs as an
in-cluster Job, never from the operator's shell), so both scripts run
inside a one-shot Job (see C below), not from the Makefile's control node.

`scenario_failover_probe.py` is a thin, single-agent, single-turn wrapper -
not a reimplementation: `AGENT=<agent>` set in its environment before it
imports `evaluations/tekos/run_scenarios.py`'s `get_token`/`auth_headers`/
`RUNTIME_URL`/`record_run_id`/`cleanup_created_runs` (same cross-agent reuse
trick `evaluations/comage/stress_test.py:74-83` already uses), posts one
chat message to `POST {RUNTIME_URL}/v1/agents/{agent}/chat`, and prints one
JSON line reporting whether the HTTP call itself succeeded.

`scenario_failover_verify.py` is the orchestrator the Job actually runs: for
each of `("comage", "sale-01")` and `("tekos", "consultant-01")`, it snapshots
`zuno_model_calls_total{agent, provider, outcome="success"}` from Thanos
Querier, invokes the probe script as a subprocess, then polls the same
Prometheus query (bounded, 150s) until some candidate's counter increases -
**not an instant before/after diff**: `zuno.model_calls`
(`components/ai-gateway/app/telemetry.py`) is pushed via OTel's
`PeriodicExportingMetricReader` (60s default export interval) to the
otel-collector, itself scraped by prometheus-k8s on a 30s interval
(`gitops/charts/observability/templates/servicemonitor-otel-collector.yaml`)
- an instant diff would false-negative on a perfectly healthy fallback.
Prints one combined JSON verdict: `{"phase": "...", "comage": {"provider":
"local-wesh", "ok": true}, "tekos": {"provider": "ovhcloud-gpt-oss-120b",
"ok": true}}`. Comage's provider is the actual fallback proof; Tekos's is
expected constant across all three phases (the decoupling control).

**B. `ansible/playbooks/day3_scenario_failover_node_inject.yml`** (new):
1. Resolve the node dynamically: `oc get pods -n zuno-ai-run -l
   app.kubernetes.io/name=qwen35-9b-wesh,kserve.io/component=workload -o
   jsonpath='{.items[0].spec.nodeName}'` and the pod name the same way -
   never hardcode the IPs seen in `wp-086`/`wp-092`. Both label keys are
   required (see the Preconditions section above for why).
2. Read `platform/ai-gateway/provider-routing.yaml`'s `cache_enabled` for
   `local-qwen35`/`local-wesh`(-`maas`) and fail with a clear message if any
   is `true` (ADR-0536 Decision 5).
3. Run the baseline probe (A). Assert Comage → `local-wesh(-maas)`, Tekos →
   `ovhcloud-gpt-oss-120b`.
4. `oc adm cordon <node>`.
5. `oc delete pod <wesh-pod> -n zuno-ai-run` - this pod only, never a
   node-wide delete (the co-located `gpt-oss-20b` pod must keep running).
6. Poll (bounded deadline, e.g. 3 minutes) for the replacement pod to reach
   `Pending` with a `FailedScheduling` event - the expected, desired outcome
   here, not a failure of the playbook.
7. Run the probe again. Assert Comage now reads `local-qwen35(-maas)`; Tekos
   unchanged (`ovhcloud-gpt-oss-120b`). Surface the ai-gateway fallback
   warning log line (`"provider '...' failed ... trying next fallback"`) as
   corroborating evidence in the output.
8. Print the verdict; exit 0 regardless of the node being left cordoned -
   that is the intended paused state, not an error.

Steps 3 and 7 (and the restore playbook's own re-probe below) are factored
into one shared, included task file, `ansible/tasks/scenario_failover_probe_job.yml`
(landed) - it runs scenario_failover_verify.py as the in-cluster Job
described in A, reusing the existing `demo-personas-password`/
`{agent}-frontend-client-secret` (zuno-auth) and `grafana-prometheus-reader-token`
(zuno-monitoring) Secrets (no new RBAC), and parses the Job's single JSON
output line into a `scenario_failover_probe_result` fact for the calling
playbook to assert against.

**C. `ansible/playbooks/day3_scenario_failover_node_restore.yml`** (new):
1. Resolve the same node/pod dynamically (do not trust state carried over
   from the inject run - re-derive it, matching this repo's "always
   re-verify" convention). **Live bug found and fixed 2026-08-30 on this
   drill's first real run:** the node can't be read from the Pending pod's
   own `spec.nodeName` - a truly unschedulable pod never gets bound to a
   node, so that field is entirely absent (not merely empty), and the
   original implementation crashed reading it. Fixed by resolving the node
   independently: list all Nodes, select the one(s) with
   `spec.unschedulable: true`, and fail loudly (not guess) unless exactly
   one is found - the pod is still used to get the pod *name* for the
   force-reschedule delete, just not the node name.
2. `oc adm uncordon <node>`.
3. `oc delete pod <wesh-pod> -n zuno-ai-run` again, to force
   rescheduling onto the now-uncordoned node (exact precedent:
   `wp-092-qwen35-wesh-targeted-anti-affinity.md:121`,
   `wp-086-spread-models-and-platform-hygiene.md:264`).
4. Poll (bounded deadline) for `Running`/`Ready`.
5. Run the probe (A) one more time. Assert Comage is back on
   `local-wesh(-maas)`; Tekos still unaffected throughout
   (`ovhcloud-gpt-oss-120b`).

**D. `Makefile`:**
- `DAY3_VERBS` (line 104): append `scenario-failover-node`.
- Add a help block in `DAY3_RECIPE`'s usage printout (after the `sign`
  block, ~line 555).
- Add a `case` branch (~after line 604), **no component argument** - this
  is a fixed scenario, not a component in the `DAY3_TEST_COMPONENTS`/
  `DAY3_BACKUP_COMPONENTS` sense, and must not be folded into
  `DAY3_COMPONENTS` (that union feeds the generic `day3 check` precheck
  dispatch, which has no `qwen35` precheck and would break). Implemented
  sequence (as landed):
  1. Refuse immediately if `[[ ! -t 0 ]]` (no TTY) - deliberate divergence
     from `stresstest`/`restore`'s "silent default in CI" pattern: this
     mutates live shared infra and must always have a human in the loop.
  2. **One** `aap_route workflow zuno-day3-scenario-failover-node-workflow
     "{}"` call for the whole scenario - not two. The workflow does not
     exist until Part B lands: **while testing Part A, force local
     execution** via `zuno_make_aap_mode: local` in
     `ansible/confidential.yml` (or an `EXTRA_VARS` override), otherwise a
     cluster with AAP reachable in `auto`/`remote` mode hard-fails instead
     of falling back (`Makefile:119-125`'s documented rc semantics).
  3. On `rc=99` (local fallback) only: run
     `day3_scenario_failover_node_inject.yml`, then a `read -r -p` pause
     (reuse the exact interactive-prompt pattern at `Makefile:569-586`)
     printing the inject-phase verdict and waiting for Enter (continue to
     restore) or Ctrl-C (abort, leaving the node cordoned - documented
     recovery path in ADR-0536's Operational considerations), then run
     `day3_scenario_failover_node_restore.yml`. On any other `rc`
     (AAP handled it, success or real failure): propagate `rc` as-is - in
     the AAP path the human pause is the Workflow Template's own approval
     node (Part B), not a second Make-level prompt.

**E. `platform/docs/check_docs.py`:** verified, no change actually needed -
`_check_one_make_command` (~lines 166-167) only validates a component when
one is present and not `all`; every doc mention of this verb in this WP/ADR
never appends one, so `python3 platform/docs/check_docs.py` already passes
against the Makefile change in D. (Initially assumed a code change would be
required here - it was not; confirmed live by running the check after D.)

### Part B - AAP version (repo work landed 2026-08-31, after Part A validated live)

**F. `gitops/charts/aap-config/templates/jobtemplate.yaml` + `values.yaml`**
(landed): two new Job Templates, `zuno-day3-scenario-failover-node-inject`
and `zuno-day3-scenario-failover-node-restore`, each pointing at its Part-A
playbook, `zuno-aap-installer` credential (mutating, same tier as
backup/restore/sign per WP-103's own rule), no survey (both playbooks
resolve their target dynamically, no per-launch choice).

**G. `gitops/charts/aap-config/templates/workflowtemplate.yaml`** (landed):
extended the rendering to support, per node, either the original
shared-Job-Template `type: job_template` shape (unchanged for all 7
pre-existing workflows - a node with no per-node `jobTemplate` still falls
back to the workflow-level default) **or a per-node `jobTemplate` override**,
plus a new `type: approval` node. The exact `workflow_nodes` shape for an
inline approval node was confirmed by reading the underlying resource
operator's own `awx.awx.workflow_job_template` module source directly
(`ansible_collections/awx/awx/plugins/modules/workflow_job_template.py`,
found locally installed on this machine) rather than against the live
Controller API - its own `EXAMPLES` block and `create_workflow_nodes`/node-
creation code confirm a `type: workflow_approval` node supplies
`name`/`description`/`timeout` directly under `unified_job_template` (no
`organization`, and no pre-existing object to look up - the approval
"template" is created inline via a
`workflow_job_template_nodes/<id>/create_approval_template/` call the
module makes itself). `helm lint`/`helm template --set aapConfig.enabled=true`
confirmed the new CRs render as expected and the 7 pre-existing workflows'
rendering is unchanged.

**H. `ansible/roles/aap_config/defaults/main.yml`** (landed): added
`zuno-day3-scenario-failover-node-inject`/`...-restore` to
`aap_config_job_templates` (both `gated: true`, `zuno-aap-installer`, no
survey) and both to `aap_config_ee_job_templates` (both playbooks shell out
to `oc adm cordon`/`uncordon` directly via `ansible.builtin.command`, same
criterion as the other 6 entries there); added
`zuno-day3-scenario-failover-node-workflow` to `aap_config_workflow_templates`
(`gated: true`). Cross-checked by hand that both lists exactly match the
chart's own `jobTemplates`/`workflowTemplates` name sets (no automated
check enforces this - "kept in sync by convention" per this file's own
header comment).

**I. Launch-RBAC:** confirmed `ansible/roles/aap_config/tasks/wire_launch_rbac.yml`
is genuinely dynamic (`aap_config_job_templates | selectattr('gated', ...)`/
same for workflow templates, no hardcoded enumeration) - the new gated
Job/Workflow Templates are picked up automatically, no code change needed
for that part. **The open question this section originally flagged - is now
answered, live, and required a real fix:** approving a `workflow_approval`
node needs a genuinely separate permission, `awx.approve_workflowjobtemplate`
- confirmed against this cluster's own `/api/controller/v2/role_metadata/`
(`awx.workflowjobtemplate`'s `allowed_permissions` lists it apart from
`execute_workflowjobtemplate`) and the Workflow Template object's own
`summary_fields.object_roles.approval_role`
("Can approve or deny a workflow approval node"). Added a new
`aap-ops-workflowjobtemplate-approver` role definition (permissions:
`[view_workflowjobtemplate, approve_workflowjobtemplate]` - Controller's own
role_definition POST rejects `approve_workflowjobtemplate` alone with a 400,
"Permissions for model workflow job template needs to include view, got:
approve_workflowjobtemplate", confirmed live via a scratch role definition
created then deleted) and granted it to `aap-ops-team` on every gated AND
ungated Workflow Template (never `aap-reader-team` - approving is a mutating
action, reader stays view-only by design). Live-verified via the Controller
API: `aap-ops-team` now holds both `aap-ops-workflowjobtemplate-executor`
and `aap-ops-workflowjobtemplate-approver` on
`zuno-day3-scenario-failover-node-workflow`; `aap-reader-team` holds only
`aap-reader-workflowjobtemplate-viewer`.

A second, unrelated bug surfaced by the same live sync: the chart's
`extra_data.target_component`, previously assumed harmless-but-unused for
these nodes, actually broke node creation entirely on Job Templates with
`ask_variables_on_launch: false` (Controller rejects `extra_data` on a
template that disallows it; the resource-operator role's `ignore_errors`
swallowed the failure, so the WorkflowTemplate CR reported `Successful`
with **zero** actual nodes - caught only by querying `workflow_nodes/`
directly, not by trusting the CR's own status). Fixed in
`templates/workflowtemplate.yaml`: `extra_data` is now only emitted for a
node with no per-node `jobTemplate` override, preserving the original
shared-Job-Template behavior for all 7 pre-existing workflows unchanged.

**J. `Makefile`:** no code change needed - the `case` branch already calls
`aap_route workflow zuno-day3-scenario-failover-node-workflow "{}"`
unconditionally (written in Part A, anticipating Part B). The CRs and RBAC
are now live-verified correct; `ansible/confidential.yml`'s
`zuno_make_aap_mode` is currently `auto` - the next `make d3
scenario-failover-node` run will genuinely attempt the AAP path end to end
(not yet exercised - see the Live verification section below).

## What NOT to touch

- Never delete or restart the `gpt-oss-20b` pod co-located on the same node
  as `qwen3.5-9b-wesh` - only cordon the node and delete the
  `qwen3.5-9b-wesh` pod specifically, by name/label.
- Do not fold `scenario-failover-node`'s pseudo-component into
  `DAY3_COMPONENTS`/`DAY3_TEST_COMPONENTS`/`DAY3_BACKUP_COMPONENTS`.
- Do not edit ADR-0526 itself to mark the fallback "proven" - its ADR file
  is immutable per this repo's convention; the gap closes via ADR-0536's own
  evidence doc plus a status update on ADR-0536, not by rewriting ADR-0526.
- Do not enable `cache_enabled` on `local-qwen35`/`local-wesh` as a side
  effect of any related work without re-reading ADR-0536 Decision 5 first.

## Acceptance checks (repo-side)

- `python3 platform/docs/check_docs.py` exits 0.
- `ansible-playbook --syntax-check` passes on both new playbooks.
- `ansible-lint` on the new playbooks/tasks shows no findings beyond this
  repo's existing pre-existing style exceptions.

## Live verification (operator step, Part A)

1. Coordinate with any other session on the shared cluster.
2. Force `zuno_make_aap_mode: local` (or `EXTRA_VARS` override).
3. Run `make d3 scenario-failover-node`, watch the inject-phase verdict,
   confirm both agents behave as expected, press Enter to restore.
4. Confirm the restore-phase verdict shows Comage back on `local-wesh` and
   Tekos still unchanged on `ovhcloud-gpt-oss-120b` throughout.
5. Record full before/during/after timestamps, `oc` output and verdict JSON
   in `docs/roadmap/evidence/adr-0536-node-failover-drill.md` (owned by this
   WP), on the template of `docs/roadmap/evidence/adr-0521-maas-local-traffic.md:90-115`.

## Live verification (operator step, Part B)

**Done, 2026-08-31.** Launched `zuno-day3-scenario-failover-node-workflow`
for real via `zuno_make_aap_mode: auto`'s `aap_route` mechanism (workflow
job 579), watched it cordon+kill the wesh pod, pause at the approval node,
approved it in the Controller UI, watched it uncordon+reschedule+restore.
Overall workflow `status: successful`, same verdicts as Part A's own
authoritative run. Full trace (including the first attempt's node-RBAC
failure and fix) in `docs/roadmap/evidence/adr-0536-node-failover-drill.md`.

## Status updates (then re-run check_docs.py)

- Done: WP-105's State is `Done`, the Phase 22 table row in
  `docs/roadmap/implementation-roadmap.md` reflects it, and
  ADR-0536's Status is flipped from `Proposed` to `Implemented` (both Parts
  A and B live-verified end to end).

## Out of scope / deferred

- Extending this drill to the other direction (killing `qwen3.5-9b` to prove
  Tekos falls back to `local-wesh`) - this was the originally-scoped drill,
  found live 2026-08-30 to be unprovable through real chat traffic: Tekos's
  only chat-reachable task is reflexional and never touches `local-qwen35`/
  `local-wesh` at all (see ADR-0536's Context). Would require a real v1 route
  for `find-relevant-docs`/`check-my-drive-docs` (Tekos's two tasks that
  *do* lead with `local-qwen35` in the routing policy but have no dispatch
  path from a chat turn) before it could be drilled the same way - a genuine
  runtime feature, not something this WP builds.
- A frontend-visible indicator of which provider answered a turn (`zuno_provider`
  is dropped well before the frontend, per ADR-0536 Decision 4) - a separate,
  larger change across agent-runtime/agent-bff/frontend, not needed to prove
  the fallback mechanism itself.
