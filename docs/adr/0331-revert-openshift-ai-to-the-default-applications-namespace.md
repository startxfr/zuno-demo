# ADR-0331: Revert OpenShift AI to the default applications namespace

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0328](0328-separate-the-openshift-ai-control-plane-from-ai-build-and-run-workload-namespaces.md) for `DSCInitialization`/`DataScienceCluster`'s `applicationsNamespace`

## Decision

Revert `DSCInitialization.spec.applicationsNamespace` and
`DataScienceCluster.spec.applicationsNamespace` from the custom
`zuno-ai-platform` (ADR-0328) back to RHOAI's own default,
`redhat-ods-applications`, and re-enable `trainer`/`ray`/`dashboard`/
`mlflowoperator` as `managementState: Managed`.

**Rationale:** by 2026-08-13, four independently-verified RHOAI 3.5 EA2
components failed under `applicationsNamespace: zuno-ai-platform`, all with
the identical root cause - the product's own bundled manifests (webhooks,
SCC/RBAC bindings, controller-manager `--namespace` flags and generated
`ClusterRole` rules) hardcode `redhat-ods-applications` rather than deriving
it from `DSCInitialization.spec.applicationsNamespace`:

- `trainer` - `ClusterTrainingRuntime` fails validation because its
  `ValidatingWebhookConfiguration` targets
  `kubeflow-trainer-controller-manager.redhat-ods-applications.svc`.
- `ray` - `kuberay-operator`'s pod is rejected by every SCC on the cluster;
  RHOAI's namespace-specific SCC/RBAC bindings only exist for the default
  namespace.
- `dashboard` - observability/Perses reconciliation fails with "unknown
  namespace for the cache" because it doesn't derive watched namespaces from
  `DSCInitialization.spec.monitoring.namespace` either.
- `mlflowoperator` - `mlflow-operator-controller-manager` CrashLoopBackOff:
  its Deployment runs `--namespace=redhat-ods-applications` unconditionally,
  and its generated `ClusterRole` grants no list/watch on `Secret`/
  `ServiceAccount`/`ConfigMap`/`Deployment`/`Job`/`CronJob`/`Service`/
  `PersistentVolumeClaim`/`ServiceMonitor` in any namespace, so
  controller-runtime's cache sync times out and the process exits.

Each was confirmed unchanged after a full operator uninstall/reinstall (not
stale state - baked into the RHOAI 3.5 EA2 manifests). With four of the
platform's own listed shared components (ADR-0328's own component diagram)
broken by the same unsupported combination, running a custom
`applicationsNamespace` on this RHOAI build is no longer viable; reverting to
the default unblocks all four without waiting on individual per-component
workarounds.

**What is unaffected:** the `zuno-ai-build`/`zuno-ai-run` workload-namespace
split (ADR-0328's other half) is untouched - `workbenchNamespace: zuno-ai-build`
and workload placement are a separate field from `applicationsNamespace` and
are not implicated in any of the four failures above.

## Operational considerations

`applicationsNamespace` is immutable once the CR exists (ADR-0328's own
Migration section documents this for the forward direction; it applies
symmetrically in reverse). Reverting requires deleting the live
`DataScienceCluster`/`DSCInitialization` CRs so `rhods-operator` recreates
every operand fresh under `redhat-ods-applications` - not just the four
broken components, every RHOAI-managed operand previously running in
`zuno-ai-platform` (`feast-operator`, `ogx-k8s-operator`, `spark-operator`,
`workload-variant-autoscaler`, `aigateway`, `trainingoperator`, `kserve`,
`modelregistry`, etc.) moves and briefly restarts during the migration
window. `redhat-ods-applications` does not need to be pre-created: RHOAI
creates its own default `applicationsNamespace` namespace as part of normal
reconciliation, unlike the custom `zuno-ai-platform` namespace ADR-0328's
Day-0 automation had to pre-create explicitly.

Once verified, `zuno-ai-platform` is empty of RHOAI operands. Whether to
remove it from `gitops/charts/namespaces/values.yaml` or repurpose it is a
follow-up decision, not required to land this revert.

## Migration / evolution

Revisit a custom `applicationsNamespace` (restoring ADR-0328's intent) once
RHOAI ships a fix for these four components, or once none of them are
required by this repository's actual feature set. Until then, any component
newly added to `DataScienceCluster.spec.components` must be verified against
the default namespace assumption before being marked `Managed` - the same
verification discipline ADR-0328 established, just against
`redhat-ods-applications` instead of a custom namespace.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives,
Consequences, Security considerations, Acceptance criteria and Review
evidence.

## Related ADRs

- [ADR-0328](0328-separate-the-openshift-ai-control-plane-from-ai-build-and-run-workload-namespaces.md) - superseded by this ADR for `applicationsNamespace`; its build/run workload-namespace split remains in effect
- [ADR-0047](0047-manage-the-complete-openshift-ai-prerequisite-lifecycle.md) - Manage the complete OpenShift AI prerequisite lifecycle (same precedent: disable what "would never have reached Ready on a real cluster")
- [ADR-0301](0301-introduce-lora-and-peft-model-customization.md) - v3 consumer of `trainer`/`ray`, the trigger to revisit a custom `applicationsNamespace` once RHOAI ships a fix
- [ADR-0302](0302-build-dataset-to-model-mlops-pipelines.md) - v3 consumer of `mlflowoperator`, same revisit trigger
