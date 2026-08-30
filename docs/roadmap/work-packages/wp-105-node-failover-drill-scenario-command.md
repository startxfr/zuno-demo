# WP-105: `make d3 scenario-failover-node` - live GPU-node failover drill (qwen-normal ↔ qwen-wesh)

- **State:** Not started.
- **ADRs:** ADR-0536 (Proposed), ADR-0418 (Implemented - `aap_route`/Workflow Template mechanism this WP extends).
- **Depends on:** WP-094 (Job Templates), WP-095 (Workflow Templates), WP-097 (make/AAP routing), WP-103 (launch-RBAC), WP-087/ADR-0526 (the qwen-normal/qwen-wesh fallback this drill proves).
- **Estimated files touched:** ~10 (2 new ADR/WP docs + 1 evidence doc, 1 new Python probe script, 2 new Ansible playbooks, Makefile, check_docs.py, roadmap tracker; Part B additionally touches the aap-config chart/role).

> Execute this brief as a standalone task from the repository root.

## Goal

Prove, live, that Tekos and Comage actually fail over between `local-qwen35`
and `local-wesh` when the model each currently prefers becomes physically
unschedulable (node cordoned, pod killed) - not just when a dependency like
MaaS goes unreachable (already drilled, ADR-0521). Package the drill as a
standing `make d3 scenario-failover-node` command, built local-first then
transposed to a full AAP Workflow Template with a human approval gate, per
this repo's own "every new make action gets both a local and an AAP path"
convention (ADR-0418 clause 6).

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

- `oc get pods -n zuno-ai-run -l app.kubernetes.io/name=qwen35-9b -o wide`
  shows exactly one `Running` pod, and `oc get pods -n zuno-ai-run -l
  app.kubernetes.io/name=qwen35-9b-wesh -o wide` shows exactly one `Running`
  pod, each on a different node - confirms the topology ADR-0536 assumes
  still holds before touching anything live.
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
"local-wesh", "ok": true}, "tekos": {"provider": "local-qwen35", "ok": true}}`.

**B. `ansible/playbooks/day3_scenario_failover_node_inject.yml`** (new):
1. Resolve the node dynamically: `oc get pods -n zuno-ai-run -l
   app.kubernetes.io/name=qwen35-9b -o jsonpath='{.items[0].spec.nodeName}'`
   and the pod name the same way - never hardcode the IPs seen in
   `wp-086`/`wp-092`.
2. Read `platform/ai-gateway/provider-routing.yaml`'s `cache_enabled` for
   `local-qwen35`/`local-wesh`(-`maas`) and fail with a clear message if any
   is `true` (ADR-0536 Decision 5).
3. Run the baseline probe (A). Assert Comage → `local-wesh`, Tekos →
   `local-qwen35`.
4. `oc adm cordon <node>`.
5. `oc delete pod <qwen35-pod> -n zuno-ai-run` - this pod only, never a
   node-wide delete (the co-located `qwen3.6-27b-instruct` pod must keep
   running).
6. Poll (bounded deadline, e.g. 3 minutes) for the replacement pod to reach
   `Pending` with a `FailedScheduling` event - the expected, desired outcome
   here, not a failure of the playbook.
7. Run the probe again. Assert Tekos now reads `local-wesh`; Comage
   unchanged. Surface the ai-gateway fallback warning log line
   (`"provider '...' failed ... trying next fallback"`) as corroborating
   evidence in the output.
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
   re-verify" convention).
2. `oc adm uncordon <node>`.
3. `oc delete pod <qwen35-pod> -n zuno-ai-run` again, to force
   rescheduling onto the now-uncordoned node (exact precedent:
   `wp-092-qwen35-wesh-targeted-anti-affinity.md:121`,
   `wp-086-spread-models-and-platform-hygiene.md:264`).
4. Poll (bounded deadline) for `Running`/`Ready`.
5. Run the probe (A) one more time. Assert Tekos is back on `local-qwen35`;
   Comage still unaffected throughout.

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

### Part B - AAP version (only after Part A is validated live)

**F. `gitops/charts/aap-config/templates/jobtemplate.yaml` + `values.yaml`:**
add two Job Templates, `zuno-day3-scenario-failover-node-inject` and
`zuno-day3-scenario-failover-node-restore`, each pointing at its Part-A
playbook, `aap-installer` credential tier (mutating, same tier as
backup/restore/sign per WP-103's own rule).

**G. `gitops/charts/aap-config/templates/workflowtemplate.yaml`:** extend
the rendering to support, per node, either the current shared-Job-Template
`type: job_template` shape **with a per-node `jobTemplate` override** (today
one Job Template is shared across every node in a workflow -
`$jobTemplate := .jobTemplate` at the top of the range, `templates/workflowtemplate.yaml:60`),
or a new `type: approval` node (`timeout`/`description`, no
`unified_job_template`). Verify the exact `workflow_nodes` argument shape
for an approval node via `oc explain workflowtemplates.tower.ansible.com.spec`
and the live Controller API before writing the CR - this repo's standing
convention, and this is new, unverified ground (no approval node exists
anywhere in the repo today).

**H. `ansible/roles/aap_config/defaults/main.yml`:** add
`zuno-day3-scenario-failover-node-workflow` to `aap_config_workflow_templates`
(`gated: true`, matching `zuno-day1-install-workflow`), with 3 nodes:
inject-job → approval → restore-job.

**I. Launch-RBAC:** per WP-103's Design section, `aap_ops`/`aap_reader`
already gain view/execute or view-only across the *full* set of Job/Workflow
Templates (gated and ungated) once `wire_launch_rbac.yml` re-runs against
whatever `values.yaml` currently lists - confirm this is genuinely dynamic
(loops over the chart's template lists rather than a hardcoded count) before
assuming no RBAC code change is needed; if it turns out to be a fixed
enumeration, extend `ansible/roles/aap_config/tasks/wire_launch_rbac.yml`
accordingly.

**J. `Makefile`:** once F-I are live, drop the "force local mode" caveat
from step D.1's comment and re-validate with `zuno_make_aap_mode: auto`.

## What NOT to touch

- Never delete or restart the `qwen3.6-27b-instruct` pod co-located on the
  same node as `qwen3.5-9b` - only cordon the node and delete the
  `qwen3.5-9b` pod specifically, by name/label.
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
4. Confirm the restore-phase verdict shows Tekos back on `local-qwen35`.
5. Record full before/during/after timestamps, `oc` output and verdict JSON
   in `docs/roadmap/evidence/adr-0536-node-failover-drill.md` (owned by this
   WP), on the template of `docs/roadmap/evidence/adr-0521-maas-local-traffic.md:90-115`.

## Live verification (operator step, Part B)

1. Re-run the same scenario via the AAP Controller UI (launch the
   `-workflow` Workflow Template, approve the manual gate node).
2. Append that run's evidence to the same evidence doc.

## Status updates (then re-run check_docs.py)

- On completion, add a row for WP-105 to the Phase 22 table in
  `docs/roadmap/v0.1-v0.3-implementation-roadmap.md` with the final State,
  and flip ADR-0536's Status from `Proposed` to `Implemented` once both
  Parts A and B are live-verified.

## Out of scope / deferred

- Extending this drill to the reverse direction (killing `local-wesh` to
  prove Comage falls back to `local-qwen35`) - same mechanism, a natural
  follow-up, not required to close ADR-0526's specific gap statement.
- A frontend-visible indicator of which provider answered a turn (`zuno_provider`
  is dropped well before the frontend, per ADR-0536 Decision 4) - a separate,
  larger change across agent-runtime/agent-bff/frontend, not needed to prove
  the fallback mechanism itself.
