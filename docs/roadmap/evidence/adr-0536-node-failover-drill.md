# ADR-0536 node-failover drill evidence

Records the live-cluster proof behind
[ADR-0536](../../adr/0536-live-node-failover-drill-for-qwen-model-fallback.md)
(GPU-node failover drill for the qwen-normal/qwen-wesh fallback). Owned by
[WP-105](../work-packages/wp-105-node-failover-drill-scenario-command.md) —
see the [implementation roadmap](../v0.1-v0.3-implementation-roadmap.md).

**Status: Part A live-verified 2026-08-30, end to end.** Part B (AAP
Workflow Template path) has not been built yet — see WP-105. ADR-0526's
"STILL NOT TRUE" caveat is now closed for the half this ADR scoped
("Comage when the [wesh] variant is unavailable"); the other half ("Tekos on
either path") stays explicitly open, unprovable through real chat traffic
today (ADR-0536's Context section).

## Part A — local path (`make d3 scenario-failover-node`, `zuno_make_aap_mode: local`)

**Run date: 2026-08-30.** Executed directly via `ansible-playbook` (not
through the `make` wrapper — the operator's shell had no allocated TTY, and
the Makefile's `scenario-failover-node` branch deliberately refuses to run
without one; the two playbooks were run manually in the same inject-then-
restore sequence the Makefile itself would have driven, including a real
human confirmation pause between them). Coordinated beforehand with the two
other live sessions on this shared cluster (`zuno-demo-56`, `zuno-demo-4c`
via cross-session messages) — both confirmed no conflicting operation on
`zuno-ai-run`/the GPU nodes before this ran.

Drills Comage's `check-deal-status` fallback (`local-wesh` → `local-qwen35`),
cordoning/killing the `qwen3.5-9b-wesh` pod, not `qwen3.5-9b` — see ADR-0536's
Context section for why the originally-scoped direction (killing `qwen3.5-9b`
to prove Tekos fails over) turned out to be unprovable through real chat
traffic. Tekos is probed throughout as a decoupling control, staying on
`ovhcloud-gpt-oss-120b` the whole time as expected.

**Node/pod:** `qwen35-9b-wesh-kserve-689595d44f-*` on
`ip-10-18-67-65.eu-west-2.compute.internal`, resolved dynamically by the
playbooks in every phase (never hand-copied).

**Sequence and verdicts (exact wall-clock timestamps were not captured — the
operator's terminal output pasted back during this run did not include
per-task timestamps; order and content below are exact, duration is not):**

1. **Baseline probe** — passed (`day3_scenario_failover_node_inject.yml`'s
   own assertion did not fire, so both conditions held): Comage on
   `local-wesh-maas`, Tekos on `ovhcloud-gpt-oss-120b`. A baseline probe
   captured moments earlier in this same session (same live routing state,
   before the pod-label target was corrected to `qwen35-9b-wesh`) recorded
   the exact provider values: `comage.provider=local-wesh-maas`,
   `tekos.provider=ovhcloud-gpt-oss-120b`, both `ok: true`.
2. **Cordon `ip-10-18-67-65...` + delete the `qwen3.5-9b-wesh` pod** —
   succeeded; the replacement pod reached `Pending` within the playbook's
   bounded wait (18 retries × 10s).
3. **Failover probe** — passed (same reasoning: the inject playbook's
   warning-only check did not fire): Comage failed over to
   `local-qwen35(-maas)`, Tekos stayed on `ovhcloud-gpt-oss-120b`.
4. **Human confirmation pause** (`read -r -p` equivalent, run manually) —
   operator reviewed the inject-phase verdict and proceeded to restore.
5. **Uncordon + delete-to-reschedule** — succeeded on the first restore
   attempt (see bugs below for what went wrong *after* this step, twice, on
   the way to a clean verdict).
6. **Restore probe** — final passing verdict, captured verbatim:
   ```json
   {"phase": "restore",
    "comage": {"provider": "local-wesh-maas", "ok": true,
      "detail": "counts_before={'local-wesh-maas': 192.0, 'local-qwen35-maas': 6.0} counts_after={'local-wesh-maas': 195.0, 'local-qwen35-maas': 6.0}"},
    "tekos": {"provider": "ovhcloud-gpt-oss-120b", "ok": true,
      "detail": "counts_before={'ovhcloud-gpt-oss-120b': 168.0} counts_after={'ovhcloud-gpt-oss-120b': 180.0}"}}
   ```
   Final pod: `qwen35-9b-wesh-kserve-689595d44f-nrf6x`, back on
   `ip-10-18-67-65.eu-west-2.compute.internal`. `PLAY RECAP`: `failed=0`.

**Real bugs found and fixed live during this run** (each committed and
pushed before the next retry — see the commit history around 2026-08-30 for
full diffs):

- The restore playbook crashed reading `spec.nodeName` off the Pending
  `qwen3.5-9b-wesh` pod — a genuinely unschedulable pod is never bound to a
  node, so that field is absent entirely, not empty. Fixed by resolving the
  cordoned node from the Node objects (`spec.unschedulable: true`) instead.
- The restore-phase probe hit a real ~30s HTTP timeout on Comage's first
  chat request against the freshly-rescheduled pod — `Running`/`Ready` only
  proves the container and its readiness probe are up, not that vLLM has
  finished loading the model onto the MIG slice. Widened to 90s (with the
  subprocess/Job/poll budgets bumped to match).
- The restore playbook wasn't safely re-runnable: a first attempt's
  uncordon+reschedule succeeded but the probe timeout above made that whole
  *attempt* fail after the infra was already fixed; re-running found zero
  cordoned nodes (correctly — there was nothing left to fix) and failed
  loudly instead of just re-verifying. Fixed by gating the cordon-hunt/
  uncordon/delete sequence on the pod's phase at the start of that specific
  run, so a Running pod skips straight to re-probing.

No cache-related false positive was observed (`cache_enabled` remains unset
for `local-qwen35`/`local-wesh` per ADR-0536 Decision 5's precondition
check, which passed silently on every run).

### Authoritative run — the real `make d3 scenario-failover-node` command

**Run date: 2026-08-30, later the same day**, after the three bug fixes
above. This is the acceptance-criteria run: the operator invoked the actual
`make d3 scenario-failover-node` command from an interactive terminal (TTY
present this time) — the Makefile's own inject → human `read -r -p` pause →
restore sequence ran exactly as designed, not the manual two-playbook
substitute used above.

Full verdict, both phases:

```json
{"phase": "baseline",
 "comage": {"provider": "local-wesh-maas", "ok": true},
 "tekos": {"provider": "ovhcloud-gpt-oss-120b", "ok": true}}
{"phase": "failover",
 "comage": {"provider": null, "ok": false, "detail": "timed out"},
 "tekos": {"provider": "ovhcloud-gpt-oss-120b", "ok": true}}
{"phase": "restore",
 "comage": {"provider": "local-wesh-maas", "ok": true},
 "tekos": {"provider": "ovhcloud-gpt-oss-120b", "ok": true}}
```

`PLAY RECAP`, both plays: `failed=0`.

**The failover-phase probe itself timed out on Comage** (`"detail": "timed
out"`, even at the widened 90s) — and this is expected, not a defect: the
inject playbook's own failover check is a `debug`-level **warning, not a
`fail`** by design (see the "Warn (do not fail)..." task), precisely because
the very first request against a mid-cutover model can exceed any
reasonable fixed timeout. The playbook printed the warning and continued to
the human pause as designed.

**Independent, more valuable confirmation: the operator manually drove the
real chat UI during the whole outage window**, for both agents, and
reported: Tekos showed no disruption at any point; Comage returned
noticeably slower responses with intermittent network errors for a period
after the cordon+kill, then began answering correctly again (via
`local-qwen35`, the fallback) once the failover settled; the same
slower/intermittent pattern recurred briefly after uncordon+reschedule
before Comage's answers were reliably served by `local-wesh` again. This
matches the automated probes exactly — the "timed out" verdict above is the
automation hitting the same real transition window a live user felt as
"network errors," not a probe bug — and is materially stronger evidence
than the JSON verdicts alone, since it confirms the actual chat experience
degrades gracefully (slow, then correct) rather than erroring outright.

**Conclusion: ADR-0536's Acceptance criteria for Part A are met.** Comage's
real chat traffic demonstrably fails over `local-wesh` → `local-qwen35` on
node/pod failure and returns to `local-wesh` on restore; Tekos is
confirmed unaffected throughout, live, via both the automated probe and
direct manual use of the chat UI.

## Part B — AAP path (Workflow Template with manual approval node)

**Repo work merged 2026-08-31** (two new Job Templates, a per-node
`jobTemplate` override plus a new `type: approval` node type in
`gitops/charts/aap-config/templates/workflowtemplate.yaml`, role
defaults/EE-assignment updated — see WP-105's own Part B section for the
full list). `helm lint`/`helm template --set aapConfig.enabled=true`
confirmed clean rendering, including that the 7 pre-existing Workflow
Templates render unchanged.

**CRs live-verified against the real Controller, 2026-08-31** (ArgoCD sync
of `zuno-aap-config-d1`, then `make d0 install aap-config` for the
launch-RBAC wiring). Two real bugs found and fixed along the way, both
hidden by a "CR Synced/Healthy proves nothing" trap — the WorkflowTemplate
CR reported `Successful` with **zero** actual workflow nodes created the
first time, caught only by querying `workflow_nodes/` directly against the
Controller API:

- The chart unconditionally sent `extra_data.target_component` on every
  `job_template`-type node, a leftover from the original shared-Job-Template
  fan-out shape. WP-105's two Job Templates have
  `ask_variables_on_launch: false` (no launch-time choice at all), and
  Controller rejects `extra_data` on a template that disallows it - the
  underlying resource-operator role's `ignore_errors` swallowed the failure
  silently (`"Unable to create workflow_job_template_node inject:
  {'extra_data': ['Variables target_component are not allowed on
  launch...']}"`). Fixed: `extra_data` is now only emitted for nodes with no
  per-node `jobTemplate` override.
- Confirmed live that approving a `workflow_approval` node needs a genuinely
  separate permission, `awx.approve_workflowjobtemplate` (this cluster's own
  `/api/controller/v2/role_metadata/` lists it apart from
  `execute_workflowjobtemplate`, and the Workflow Template's own
  `object_roles` always carries a distinct `approval_role`) - this **answers
  WP-105's own open question**: the existing execute grant was NOT
  sufficient. A follow-up bug: Controller's `role_definitions` endpoint
  rejects a custom role for `workflowjobtemplate` missing `view` (`400
  "Permissions for model workflow job template needs to include view, got:
  approve_workflowjobtemplate"`) - fixed by bundling
  `view_workflowjobtemplate` alongside `approve_workflowjobtemplate` in the
  new `aap-ops-workflowjobtemplate-approver` role definition.

**Final live-verified state**, confirmed via the Controller API directly:
- `workflow_job_templates/63/workflow_nodes/` — 3 nodes: `inject` (job,
  `zuno-day3-scenario-failover-node-inject`), `approve-restore`
  (`workflow_approval`, name "Confirm the failover, then approve to
  uncordon+restore"), `restore` (job,
  `zuno-day3-scenario-failover-node-restore`).
- `role_team_assignments` on that workflow: `aap-ops-team` holds both
  `aap-ops-workflowjobtemplate-executor` and the new
  `aap-ops-workflowjobtemplate-approver`; `aap-reader-team` holds only
  `aap-reader-workflowjobtemplate-viewer` (view-only, as designed - never
  granted approve).

**Still not exercised: an actual end-to-end run through the AAP path** -
launching the Workflow Template, approving the paused node in the
Controller UI, and confirming both Job Templates' logs and the same
Comage/Tekos provider verdicts as Part A. The CRs and RBAC are proven
correct; a live run through them (with `zuno_make_aap_mode: auto`) is the
one remaining step to fully close WP-105.
