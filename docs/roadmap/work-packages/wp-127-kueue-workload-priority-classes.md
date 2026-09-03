# WP-127: design Kueue WorkloadPriorityClass tiers for zuno-ai-run

- **State:** Not started
- **ADRs:** ADR-0545 (decision 2, started here)
- **Depends on:** WP-117 (Done, 2026-09-03 - GPU-MIG ResourceFlavor + ClusterQueue quota,
  LocalQueue and namespace enrolment for `zuno-ai-run`)
- **Related:** [ADR-0542](../../adr/0542-autoscale-one-served-model-through-llminferenceservice-spec-scaling.md)
  (the saturated-quota measurement motivating this WP),
  [ADR-0321](../../adr/0321-delegate-kueue-lifecycle-to-the-red-hat-build-of-kueue-operator.md)

> **Design/research WP - no live change.** This WP produces a proposal and a dry-run validation
> only. Applying priority classes live is a separate, future WP once the proposal is reviewed.

## Goal

The GPU `ResourceQuota` for `zuno-ai-run` is saturated (`mig-1g.24gb` 3/3, `mig-2g.48gb` 2/2,
WP-121) and every `Workload` - client-facing agent inference and internal batch alike
(`job-*-mmlu-cache-prefetch`, `job-garak-*`, `job-ragas-eval`, `job-zuno-day2-stresstest-*`) -
shares the same `LocalQueue` with no priority differentiation. Propose a small set of
`WorkloadPriorityClass` tiers so agent-serving inference is never queued behind internal batch
under saturation, and validate the proposal without applying it.

## Preconditions (verify before starting)

- WP-117 merged; the `default` `ClusterQueue`/`LocalQueue`/`ResourceFlavor` set is live.
- Read the current live `Workload` objects (`oc get workload -n zuno-ai-run -o yaml`) to confirm
  how each type is admitted today - no `priorityClassName` is set anywhere at present (per this
  ADR's own live inventory), so today's admission order is effectively FIFO within the shared
  queue.

## Repo changes (step by step)

1. Inventory every Job-producing component that lands a `Workload` in `zuno-ai-run` today:
   agent-serving `LLMInferenceService` Deployments (via KServe, not a batch `Job`), `LMEvalJob`
   (MMLU), `GuardrailsOrchestrator`-driven scans (garak), `job-ragas-eval`, and the
   `day2-stresstest` Jobs per persona. Confirm which of these are actually Kueue-managed
   `Workload`s versus KServe-managed Deployments outside Kueue's admission path - only the former
   are addressable by `WorkloadPriorityClass`.
2. Draft `WorkloadPriorityClass` CRs (e.g. `agent-serving` high, `evaluation` medium,
   `stresstest` low) as a new template alongside `gitops/charts/kueue/templates/
   queue-resources.yaml`, values-gated and **not enabled by default**.
3. Map which components would set which class (via pod-template `priorityClassName`, which Kueue
   reads to prioritize `Workload` admission) - as a design note, not a live label change.
4. Produce a written before/after comparison: under the current saturated quota, simulate how a
   burst of `day2-stresstest` Jobs would today delay a concurrent agent-serving admission, versus
   how the proposed tiers would change that ordering.

## What NOT to touch

Do not apply any `priorityClassName` to a live pod template or enable the new
`WorkloadPriorityClass` objects by default. Do not touch the `ClusterQueue`/`ResourceFlavor` quota
sizing WP-117/ADR-0538 decision 3 established - this WP adds ordering within the existing quota,
it does not resize it.

## Acceptance checks

- `helm template` / `oc apply --dry-run=server` on the drafted `WorkloadPriorityClass` objects is
  clean.
- The written comparison note is concrete (real observed Workload counts/timings from the
  inventory step, not a hypothetical).
- No live `Workload` or `LocalQueue` behavior has changed as a result of this WP.

## Operator / human follow-up (not executable by the model)

Review and approve the proposed tier boundaries before any follow-up WP applies them live.

## Status updates (then re-run check_docs.py)

On completion: this WP's `- **State:**` line and tracker row move together; ADR-0545 is not
reopened by this WP's completion (a future ADR/WP decides on live adoption).

## Out of scope / deferred

Live application of any priority class. Preemption/borrowing policy (Kueue `Cohort`, already
explicitly not adopted per ADR-0545 decision 5) - out of scope unless this WP's findings show a
concrete need, which would require a new ADR.
