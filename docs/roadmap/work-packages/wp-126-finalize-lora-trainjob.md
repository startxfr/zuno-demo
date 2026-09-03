# WP-126: finalize the LoRA TrainJob (lift WP-119's "shipped disabled")

- **State:** Operator pending (2026-09-03)
- **ADRs:** ADR-0545 (decision 1), ADR-0539, ADR-0538
- **Depends on:** WP-119 (Repo work merged, 2026-09-02)
- **Related:** [ADR-0351](../../adr/0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md)
  (the burst-node mechanism this WP's live run exercises)

> **Live cluster action - requires explicit operator go-ahead before execution.** Flipping the
> flag and running a real LoRA job triggers a genuine `MachineAutoscaler` scale-up of
> `zuno-gpu-burst-a` from zero. Do not run the live steps without confirming first.

## Goal

WP-119 built and merged the whole mechanism - a KFP step that submits a Kubeflow `TrainJob` to
the namespaced `mlops-lora` `TrainingRuntime` and waits - but shipped it disabled
(`training.trainJob.enabled: false`). This WP turns it on and proves it end to end with one real
LoRA training run, closing the gap the Kubeflow Trainer controller has had since install (15
`ClusterTrainingRuntime`s usable, zero consumers).

## Preconditions (verify before starting)

- WP-119 merged; `components/mlops/src/trainjob.py`, `gitops/charts/mlops/templates/
  trainingruntime.yaml` and the widened RBAC (`pipeline-runner-mlops-dspa`) are in place.
- `zuno-gpu-burst-a`'s `MachineAutoscaler` (min 0 / max 1) is healthy and not already scaled up for
  an unrelated reason.
- Confirm live whether the burst node's GPU allocation is isolated from the MIG `ResourceFlavor`
  quota that WP-121 found saturated (`mig-1g.24gb` 3/3, `mig-2g.48gb` 2/2) - the burst node is a
  separate, non-MIG `g7e.2xlarge` per ADR-0351, but verify this against the live `ResourceFlavor`/
  `ClusterQueue` before assuming it is unaffected.

## Repo changes (step by step) - Done, live-verified 2026-09-03

1. Flipped `training.trainJob.enabled: true` in `gitops/charts/mlops/values.yaml` (commit
   `9a0b7303`).
2. **Found and fixed a latent defect `helm template`/`helm lint` could not catch.**
   `mlPolicy.torch.numProcPerNode` rendered as a quoted `"1"` string; the `TrainingRuntime` CRD's
   CEL validation rejects that outright (`'no such overload'` - neither the string-enum branch
   ("auto"/"cpu"/"gpu") nor the int branch matches a quoted numeral). Caught only by
   `oc apply --dry-run=server` against the live cluster, never live-tested since WP-119 merged it
   disabled. Fixed to a bare YAML integer (`numProcPerNode: 1`), same commit.
3. **Preconditions verified live before flipping anything:**
   `zuno-gpu-burst-a`'s `MachineAutoscaler` (min 0/max 1) healthy at 0 replicas, not already
   scaled up. GPU isolation from the saturated MIG `ClusterQueue` quota (ADR-0542) confirmed on
   three independent axes: `zuno-mlops` carries no `kueue.openshift.io/managed` label (not
   Kueue-enrolled at all), the runtime requests `nvidia.com/gpu` (a whole GPU, never
   `nvidia.com/mig-*`), and its `nodeSelector` targets `machine.startx.io/group: gpu-burst` - a
   node group distinct from the two permanent MIG nodes' `group: gpu`.
4. Pushed (`9a0b7303`) and let ArgoCD's `automated`/`selfHeal` sync pick it up - confirmed
   `Synced`/`Healthy`, `op=Succeeded`.
5. **Live-verified the actual cluster objects**, not just the sync status:
   `trainingruntime.trainer.kubeflow.org/mlops-lora` exists in `zuno-mlops` with
   `spec.mlPolicy: {numNodes: 1, torch: {numProcPerNode: 1}}` (the fixed integer, confirmed
   server-accepted); the `zuno-mlops-d1-mlops` Role now carries the four widened rule blocks
   (`trainjobs` create/get/list/watch/delete, `trainingruntimes`/`jobsets`/`pods`/`pods/log`/
   `events` read-only) and its RoleBinding lists both `zuno-mlops-d1-mlops` and
   `pipeline-runner-mlops-dspa` as subjects - exactly WP-119's documented requirement.

## Live actions (confirm before running)

1. Trigger the `mlops` KFP pipeline's LoRA training stage for a real run (the same wesh-style
   dataset WP-119/ADR-0526 already used, unless a different real case is preferred).
2. Watch the JobSet-owned pod actually materialize on `zuno-gpu-burst-a` from a scaled-from-zero
   node - this is the one step WP-119 explicitly left unverified ("the scale-from-zero probe for a
   JobSet-owned pod").
3. Confirm the `TrainJob` reaches a terminal `Complete` condition and `mlops.py`'s
   `train_manifest.json` verification against S3 passes (per WP-119, it does not trust the
   `Complete` condition alone).

## What NOT to touch

`components/mlops/src/trainjob.py`'s submit/adopt/poll logic and the RBAC - correct as WP-119 left
them. The `TrainingRuntime` definition needed one field-level fix (`numProcPerNode`, above) that
WP-119 could not have caught without a live dry-run; nothing else about it changed. This WP is the
flag flip plus that fix plus the live proof, not a mechanism redesign.

## Acceptance checks

- `TrainJob` reaches `Complete`; the JobSet-owned pod's node is confirmed as the scaled-up
  `zuno-gpu-burst-a`, not silently scheduled elsewhere.
- `train_manifest.json` lands in S3; the run is visible in MLflow (WP-116's tracking).
- `zuno-gpu-burst-a` scales back to zero afterward (`unneededTime: 10m` per ADR-0351) - confirm
  the scale-down actually happens, not just that scale-up did.
- Rollback is a pure flag revert (`training.trainJob.enabled: false`) - no infrastructure is left
  behind if the run needs to be reverted.

## Operator / human follow-up (not executable by the model)

Explicit confirmation before the live actions section (real GPU node scale-up). Sign-off on the
LoRA run's output quality if it differs from a prior known-good baseline.

## Status updates (then re-run check_docs.py)

On completion: update this WP's `- **State:**` line and its tracker row together; reflect the live
run's outcome in ADR-0539's `**Status:**` line (still `Accepted` unless the live proof moves it
toward `Implemented` - judge against ADR-0539's own stated scope, not this brief).

## Out of scope / deferred

Raising `maxReplicas`/distributed multi-node training (no documented need, ADR-0545 decision 5).
A second fine-tuning use case beyond the existing `-wesh` case - none is currently planned.
