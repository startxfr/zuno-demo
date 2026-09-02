# ADR-0539: Delegate LoRA training compute to a KFP-submitted Kubeflow TrainJob

- **Status:** Accepted
- **Target:** v0.7
- **Date:** 2026-09-02
- **Decision owners:** Zuno Demo architecture team

## Context

The LoRA fine-tuning step runs as an ordinary KFP container component. Its GPU placement — a
whole `nvidia.com/gpu`, the `machine.startx.io/group=gpu-burst` node selector and the
`zuno.io/gpu-burst` toleration that together trigger ADR-0351's scale-from-zero burst node — is
expressed as six Kubeflow SDK calls inside `gitops/charts/mlops/files/pipeline.py.tpl`. That is
platform configuration written as Python inside a compiled DAG: invisible to anyone reading the
chart, changeable only by recompiling and re-uploading an immutable `PipelineVersion`, and
duplicated in intent with the `training.gpu`/`training.resources` values it interpolates.

Meanwhile the Kubeflow Trainer 2.1 controller runs on this cluster with 15 usable
`ClusterTrainingRuntime`s, and nothing in this repository submits a single `TrainJob`. ADR-0538
decision 4 deferred adoption and named the conforming future shape precisely — *"a KFP step
submitting a TrainJob/RayJob (KFP stays the orchestrator; the step delegates the compute)"* —
and named "a later ADR once a distributed-training need exists" as the vehicle. This is that
ADR, arriving before distributed training exists because the configuration-in-Git argument stands
on its own.

Live findings that shaped the design:

- `TrainJob.spec.trainer` exists (`{image, command, args, env, numNodes, numProcPerNode,
  resourcesPerNode}`). It is the whole mechanism: a step can submit a job that runs the existing
  entrypoint with forwarded env, with no `podTemplateOverrides` gymnastics.
- All 15 `ClusterTrainingRuntime`s carry `ownerReferences` to `Trainer/default-trainer`, so any
  edit is reverted on the operator's next reconcile.
- `spec.trainer.env` accepts only `name/value/valueFrom` — there is no `envFrom`.

## Decision

1. **KFP still orchestrates; one step's compute moves.** `train-lora` becomes a dispatcher: with
   `MLOPS_TRAINJOB_ENABLED=true` it submits a `TrainJob` and blocks on it, otherwise it runs
   in-process exactly as before. ADR-0302 decision 1 is unchanged and re-affirmed — KFP keeps the
   DAG, the ordering, the caching and the ADR-0107 gate.
2. **A namespaced `TrainingRuntime`, not a `ClusterTrainingRuntime`.** `mlops-lora` in
   `zuno-mlops` carries the image, GPU request, node selector, toleration and ServiceAccount as
   chart configuration in Git. Reusing an unmodified cluster runtime would instead mean restating
   all of that on every `TrainJob`, i.e. in submitter-generated ephemeral YAML, which inverts this
   repo's values-driven convention. `spec.runtimeRef` is immutable and same-namespace, which
   points the same way.
3. **The training code does not change, and is not deleted.** `_run_lora_training()` and its
   helpers move from a KFP pod to a `TrainJob` pod, reachable as the new CLI stage
   `train-lora-local` — which is also what the trainer pod executes, so the dispatcher cannot
   recurse. Deleting them would require adopting a `training-hub` runtime, at the cost of five
   named capabilities: the anchored `loraTargetModules` regex (80 modules matched, zero `mtp.*`
   or `model.visual.*`), the fail-loud "LoRA matched no modules" guard,
   `_assert_no_fully_masked`, exact prompt-length masking, and the held-out generation the
   ADR-0107 gate consumes. That alternative is explicitly deferred, not rejected on principle.
4. **Credentials are never literal values in a `TrainJob` spec.** Configuration is forwarded by
   prefix allowlist as plain values; `AWS_*` and `PG{USER,PASSWORD}` are forwarded as
   `valueFrom.secretKeyRef`; the acceptance-gate secrets are not forwarded at all, because only
   `evaluate` needs them and `evaluate` stays a KFP step. A plaintext credential in a `TrainJob`
   spec would sit in etcd readable by anyone holding `get trainjobs` in the namespace, so this is
   a unit-tested property rather than a convention.
5. **Off by default.** `training.trainJob.enabled: false` is the shipped state and the one-value
   rollback. The in-process branch — including its GPU wiring — is therefore kept rather than
   deleted: removing it would make the rollback silently GPU-less.

## Non-goals

Moving any other stage off KFP; adopting a `training-hub` runtime (decision 3 names the five
losses); distributed training — `numNodes: 1` is what the current workload needs; Kueue-queueing
the TrainJob (ADR-0538 decision 3's operand integrates the `BatchJob` framework only and
`zuno-mlops` gets no LocalQueue, so there is no interaction).

## Operational considerations

- **The step's failure contract is unchanged and must stay that way.** A failed or timed-out
  `TrainJob`, or a completed one whose `train_manifest.json` is absent from S3, raises
  `SystemExit`, so the KFP task exits non-zero and `.after()` stops `merge-export`. The
  manifest check exists because a Complete `TrainJob` with missing artifacts is otherwise a silent
  data-loss bug that surfaces later and further from its cause.
- **The controller's condition vocabulary is not pinned by the CRD.** The terminal-state reader
  treats anything it does not recognise as *still running*, never as success — guessing "done"
  would let `merge-export` start against a model that was never written.
- **`PipelineVersion` specs are immutable.** This change bumps `pipeline.version` to `v0-2-1`.
  Re-applying under an existing name is rejected and the old spec silently stays in force.
- **A `TrainJob` labelled with a completed run is adopted rather than resubmitted**, so a KFP
  retry costs seconds instead of ~2h of burst-node GPU.
- **Unverified until a live run**: whether the ClusterAutoscaler carries MachineSet template
  labels into its simulated node for a *JobSet-owned* pod during scale-from-zero. If not, the
  TrainJob pends until timeout; ADR-0351 already names the fallback (drop the node selector, keep
  the toleration and the whole-GPU request). Probe with a short CPU-only TrainJob before spending
  a real run.
- The image's `COPY` directives are per-file, not `COPY src/`, so a new module absent from the
  Containerfile does not exist in the image and fails at runtime in a pod no local test exercises.
  `trainjob.py` is copied explicitly for that reason.

## Migration / evolution

Executed by [WP-119](../roadmap/work-packages/wp-119-kfp-submitted-trainjob.md). Future: enabling
it after the scale-from-zero probe; distributed training via `numNodes > 1` if a need appears; and
the `training-hub` runtime alternative if its five capability gaps are ever closed upstream.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Consequences,
Security considerations, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0538](0538-adopt-rhoai-35-workload-surfaces-mlflow-kueue-trainingjobs.md) - **amended**:
  decision 4 deferred TrainJob adoption and named this shape and this vehicle.
- [ADR-0302](0302-build-dataset-to-model-mlops-pipelines.md) - decision 1 (KFP stays the
  orchestrator) is re-affirmed, not weakened.
- [ADR-0301](0301-introduce-lora-and-peft-model-customization.md),
  [ADR-0526](0526-fine-tune-and-serve-a-french-urban-register-model-variant.md) - the LoRA flow
  whose compute this relocates.
- [ADR-0107](0107-introduce-automated-model-quality-gates.md) - the promotion gate whose inputs
  the relocated step still produces.
- [ADR-0351](0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md) -
  the burst node, and the documented node-selector fallback.
