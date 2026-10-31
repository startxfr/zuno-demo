# KServe feature request draft: a rollout strategy on LLMInferenceService (2026-10-25)

To file upstream (KServe, `LLMInferenceService` controller). Written for maintainers who do
not know Zuno.

**Title.** LLMInferenceService: allow setting the Deployment rollout strategy (Recreate /
maxSurge 0)

**Problem.** An `LLMInferenceService` that requests one GPU, or one MIG slice, in a namespace
whose ResourceQuota has no spare GPU cannot roll out any spec change. The generated
Deployment uses the default RollingUpdate (maxSurge 25%, so one extra pod for one replica).
The surge pod is refused by the quota (`FailedCreate … exceeded quota`), and the old pod keeps
serving the old spec. The rollout never progresses and ends in `ProgressDeadlineExceeded`.

`LLMInferenceService` v1alpha2 (`serving.kserve.io`) has no strategy field. The controller
owns `spec.strategy` of the Deployment (managedFields, Update), so setting it on the
Deployment is reverted.

**Today's workaround.** Scale the old ReplicaSet to 0 by hand. If the new ReplicaSet has gone
into exponential backoff after long FailedCreate, delete it so the Deployment recreates it.

**Proposal.** Expose the strategy on the `LLMInferenceService` workload template, for example
`spec.template.strategy` or a `spec.deploymentStrategy` like `InferenceService`'s
`deploymentStrategy`, and copy it to the generated Deployment(s). With `Recreate` (or
`rollingUpdate.maxSurge: 0, maxUnavailable: 1`), a single-GPU model rolls out within its quota,
at the cost of a short outage the operator chose.

**Environment where seen.** OpenShift AI 3.5 (KServe LLMInferenceService v1alpha2), MIG slices
`nvidia.com/mig-1g.24gb` and `mig-2g.48gb`, a namespace quota equal to the slices in use.
