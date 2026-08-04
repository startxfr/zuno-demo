# models

Applies `gitops/apps/models` (`gitops/charts/models`): a KServe
`ServingRuntime` (vLLM) + `InferenceService` serving Qwen2.5-7B-Instruct on
the single 24GB L4 (ADR-0019). CONFIG_SCOPE only — no separate prepare
phase. Depends on `openshift_ai` (`DataScienceCluster` Ready) and
`nvidia_gpu` (GPU Operator) having run first.
