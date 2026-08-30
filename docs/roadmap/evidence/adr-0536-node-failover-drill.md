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

## Part B — AAP path (Workflow Template with manual approval node)

_Not yet run — depends on Part A closing first, and on the
`gitops/charts/aap-config` Workflow Template rendering extension (WP-105
Part B) actually landing._

Expected to record the same verdicts as Part A, plus the Controller job/
workflow-job ids and the operator who approved the manual gate.
