# ADR-0536 node-failover drill evidence

Records the live-cluster proof behind
[ADR-0536](../../adr/0536-live-node-failover-drill-for-qwen-model-fallback.md)
(GPU-node failover drill for the qwen-normal/qwen-wesh fallback). Owned by
[WP-105](../work-packages/wp-105-node-failover-drill-scenario-command.md) —
see the [implementation roadmap](../v0.1-v0.3-implementation-roadmap.md).

**Status: not yet run.** This file is a placeholder skeleton, created
alongside WP-105/ADR-0536, to be filled in the first time `make d3
scenario-failover-node` actually executes against a live cluster (Part A),
and appended to again once the AAP Workflow Template path (Part B) is
exercised. Until both sections below carry real timestamps and verdicts,
ADR-0526's "STILL NOT TRUE" fallback caveat remains in force — do not cite
this scenario as proven from this file's presence alone.

## Part A — local path (`make d3 scenario-failover-node`, `zuno_make_aap_mode: local`)

_Not yet run._

Drills Comage's `check-deal-status` fallback (`local-wesh` → `local-qwen35`),
cordoning/killing the `qwen3.5-9b-wesh` pod, not `qwen3.5-9b` — see ADR-0536's
Context section for why the originally-scoped direction (killing `qwen3.5-9b`
to prove Tekos fails over) turned out to be unprovable through real chat
traffic. Tekos is probed throughout as a decoupling control, expected to stay
on `ovhcloud-gpt-oss-120b` the whole time.

Expected to record, per run:

- Node/pod resolved dynamically (name, not assumed from a prior write-up).
- Baseline probe verdict (Comage → `local-wesh(-maas)`, Tekos →
  `ovhcloud-gpt-oss-120b`).
- Cordon/delete timestamps, and the `Pending`/`FailedScheduling` confirmation
  with its own timestamp.
- Failover probe verdict (Comage → `local-qwen35(-maas)`, Tekos unchanged),
  plus the corroborating ai-gateway fallback warning log line.
- Uncordon/reschedule timestamps, and the `Running`/`Ready` confirmation.
- Restore probe verdict (Comage back on `local-wesh(-maas)`, Tekos still
  unchanged).
- Total wall-clock time cordoned, and any anomaly observed.

## Part B — AAP path (Workflow Template with manual approval node)

_Not yet run — depends on Part A closing first, and on the
`gitops/charts/aap-config` Workflow Template rendering extension (WP-105
Part B) actually landing._

Expected to record the same verdicts as Part A, plus the Controller job/
workflow-job ids and the operator who approved the manual gate.
