# models

Applies `gitops/apps/models` (`gitops/charts/models`): a KServe
`ServingRuntime` (vLLM) + `InferenceService` serving Qwen2.5-7B-Instruct on
the single 24GB L4 (ADR-0019). CONFIG_SCOPE only - no separate prepare
phase. Depends on `openshift_ai` (`DataScienceCluster` Ready) and
`nvidia_gpu` (GPU Operator) having run first.

`tasks/discover_vllm_image.yml` (ADR-0048) - included by both
`tasks/precheck.yml` and `tasks/configure.yml` - discovers the vLLM
serving-runtime image Red Hat OpenShift AI actually published for this
cluster/catalog instead of trusting `gitops/charts/models/values.yaml`'s
hardcoded fallback; see that chart's own README for the full mechanism.
