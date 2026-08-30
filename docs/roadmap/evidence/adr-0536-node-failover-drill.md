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

Expected to record, per run:

- Node/pod resolved dynamically (name, not assumed from a prior write-up).
- Baseline probe verdict (Comage → `local-wesh`, Tekos → `local-qwen35`).
- Cordon/delete timestamps, and the `Pending`/`FailedScheduling` confirmation
  with its own timestamp.
- Failover probe verdict (Comage unchanged, Tekos → `local-wesh`), plus the
  corroborating ai-gateway fallback warning log line.
- Uncordon/reschedule timestamps, and the `Running`/`Ready` confirmation.
- Restore probe verdict (Tekos back on `local-qwen35`).
- Total wall-clock time cordoned, and any anomaly observed.

## Part B — AAP path (Workflow Template with manual approval node)

_Not yet run — depends on Part A closing first, and on the
`gitops/charts/aap-config` Workflow Template rendering extension (WP-105
Part B) actually landing._

Expected to record the same verdicts as Part A, plus the Controller job/
workflow-job ids and the operator who approved the manual gate.
