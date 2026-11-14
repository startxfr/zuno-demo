# WP-283: Check that a pod without a node selector schedules, for the UnifAI canary

- **State:** Not started
- **ADRs:** [ADR-0614](../../adr/0614-split-the-cluster-into-infra-general-worker-and-gpu-node-pools.md) (node pools)
- **Depends on:** [WP-260](wp-260-roll-out-the-infra-general-and-gpu-node-pools-on-demo333.md) (the pools on demo333)
- **Estimated files touched:** ~6 (a check playbook and its `make` target, a Role in the chart that owns the namespace, the runbook)

> Opened 2026-11-14. The owner validated the point the same day in the UnifAI review held with unifai-compare (drift point
> 4) and chose to plan it rather than build it that night. Planned before the UnifAI 0.1 freeze of 2026-12-01; the live
> proof needs the owner's go.

## Why

Since ADR-0614, the UnifAI fork's canary runs its e2e pods with `E2E_NODE_SELECTOR` empty. It relies on the scheduler
placing a pod without a node selector on a general worker. Nothing checks that assumption on our side. A taint, a quota
or a full pool would leave the canary pods `Pending`, and the canary would look broken while the release is fine.

## Content

1. `make d2 check canary-ready`:
   - start a throwaway pod with no node selector and no toleration, in the namespace the canary uses;
   - fail when it stays `Pending` past a timeout, and print the scheduler's event;
   - delete it with `propagationPolicy: Background`, or give it a TTL, so nothing is orphaned.
2. **Permissions.** The AAP check identity (`zuno-aap/aap-day0-check`) can only read. Add a targeted Role in the chart
   that owns the namespace: `create` and `delete` on pods, limited by name where possible (ADR-0354). Prove the check
   through AAP, not only with kube:admin.
3. **Runbook.** In `docs/platform/operations.md`, list what the fork's canary assumes of the cluster:
   - a schedulable pod without a node selector;
   - the opted-in namespace and its admission policies;
   - the signatures in the internal Quay (WP-282);
   - its quota.
   Each assumption gets the command that checks it.

## Acceptance

- The check passes on demo333 through AAP. It fails, with the scheduler's reason, when the namespace has a pod quota of
  zero; this negative test runs in a rehearsal namespace.
- No pod or Job is left behind.
- The runbook section exists and unifai-compare confirms it matches what the canary assumes.
