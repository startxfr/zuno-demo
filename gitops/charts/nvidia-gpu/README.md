# nvidia-gpu

Referenced by `gitops/apps/nvidia-gpu/application.yaml`. Installs the
NVIDIA GPU Operator (sync-wave `"10"`: `Namespace` + `OperatorGroup` +
`Subscription`) and its `ClusterPolicy` (sync-wave `"20"`).

## Why the ClusterPolicy isn't in this chart's Git history

Every OLM-published operator ships its own recommended default CR in its
CSV's `alm-examples` annotation. A hand-maintained `ClusterPolicy` spec
was rejected outright on a real cluster (GPU Operator v26.3.3): "spec.
daemonsets: Required value, spec.dcgm: Required value, ..." - the
required top-level shape changes between operator releases, so this
chart never hand-maintains it (same ADR-0047/ADR-0310 reasoning that
applied before ADR-0312).

Instead, `values.yaml`'s `clusterPolicy: {}` renders nothing from
`templates/clusterpolicy.yaml` by default, and `ansible/roles/
nvidia_gpu/tasks/install.yml` calls `ansible/tasks/apply_gitops_app.yml`
**twice**:

1. With no extra Helm values - the `Application` syncs only wave 10
   (Namespace/OperatorGroup/Subscription). Waits for it `Healthy` (the
   custom `Subscription` health check from `ansible/roles/argocd/tasks/
   apply_resource_health_checks.yml`, ADR-0312).
2. The role then reads the now-installed CSV's `alm-examples` (same
   `kubernetes.core.k8s_info` lookups as before ADR-0312) and calls
   `apply_gitops_app.yml` again with `gitops_app_extra_helm_values:
   {clusterPolicy: {spec: <discovered>}}` - this updates the same
   `Application`'s `spec.source.helm.values`, and ArgoCD syncs the now
   non-empty wave 20 `ClusterPolicy`.

The role never applies the `ClusterPolicy` object itself with
`kubernetes.core.k8s` - both steps go through an `Application`
create/update, keeping the "role only creates/updates its ArgoCD
Application" property from ADR-0312 even though the discovery is
inherently two-phase (the spec cannot be known before the operator this
same chart installs has actually installed a CSV to read it from).
