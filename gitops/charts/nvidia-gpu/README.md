# nvidia-gpu

Thin wrapper around the startx `cluster-gpu` chart (vendored Helm
dependency - this chart has no `templates/` directory of its own; every
object, including the `ClusterPolicy`, is rendered by the subchart).
Referenced by `gitops/apps/nvidia-gpu/application-d0.yaml`
(`cluster-gpu.project.enabled` + `cluster-gpu.operator.enabled`:
`Namespace` + `OperatorGroup` + `Subscription`) and `application-d1.yaml`
(`cluster-gpu.gpu.{enabled,name,spec}`: the `ClusterPolicy`) - two
separate Applications, each applied independently.

## Why the ClusterPolicy isn't in this chart's Git history

Every OLM-published operator ships its own recommended default CR in its
CSV's `alm-examples` annotation. A hand-maintained `ClusterPolicy` spec
was rejected outright on a real cluster (GPU Operator v26.3.3): "spec.
daemonsets: Required value, spec.dcgm: Required value, ..." - the
required top-level shape changes between operator releases, so this
chart never hand-maintains it.

Instead, `values.yaml`'s `cluster-gpu.gpu: {enabled: false, spec: "{}"}`
renders nothing by default (`gpu.spec` must be a pre-serialized YAML
*string*, not a map - the subchart inserts it via `nindent`), and
`ansible/roles/nvidia_gpu/tasks/install.yml` calls
`ansible/tasks/apply_gitops_app.yml` **twice**, against two different
Applications:

1. `gitops_app_phase: d0` - applies `zuno-nvidia-gpu-d0`
   (`operator.enabled: true`, no `ClusterPolicy` concept at all on this
   side). Waits for it `Healthy` (the custom `Subscription` health check
   from `ansible/roles/argocd/tasks/apply_resource_health_checks.yml`).
2. The role then reads the now-installed CSV's `alm-examples` and calls
   `apply_gitops_app.yml` again, `gitops_app_phase: d1`, applying
   `zuno-nvidia-gpu-d1` for the first time already with
   `gitops_app_extra_helm_values: {cluster-gpu: {gpu: {enabled: true,
   spec: <discovered + overlaid>}}}` - no preliminary empty render needed.

The role never applies the `ClusterPolicy` object itself with
`kubernetes.core.k8s` - both steps go through an `Application`
create/update, keeping the "role only creates/updates its ArgoCD
Applications" property even though the discovery is inherently two-phase.

## The zuno overlay on the discovered spec (ADR-0351)

Between discovery and apply, the role `combine`s two overrides into the
CSV's default spec (see the comment block in
`ansible/roles/nvidia_gpu/tasks/install.yml`):

- `mig.strategy: mixed` - the permanent GPU node
  (`gitops/charts/machines`'s `zuno-gpu-a`) is MIG-partitioned
  `all-balanced` (2x 1g.24gb + 1x 2g.48gb slices, advertised as
  `nvidia.com/mig-*` resources) while the burst node keeps its whole GPU
  as `nvidia.com/gpu` - only the `mixed` strategy supports both resource
  shapes in one cluster. Which node gets which partition is per-node
  (`nvidia.com/mig.config` labels set by the `machines` chart's
  MachineSets), not part of this spec.
- `daemonsets.tolerations` - the GPU-operator operands only tolerate
  `nvidia.com/gpu:NoSchedule` by default (verified live 2026-08-17); the
  overlay adds `zuno.io/gpu-burst` so the driver/device-plugin can start
  on the tainted burst node at all.

**Day-2 changes to either override go through a role re-run**
(`make day0 install nvidia-gpu`): `zuno-nvidia-gpu-d1` has
`selfHeal: true` and owns the full spec through its helm values, so a
live `oc patch clusterpolicy` is silently reverted on the next sync.
