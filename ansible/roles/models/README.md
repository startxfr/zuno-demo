# models

Applies `gitops/apps/models` (`gitops/charts/models`): a KServe
`ServingRuntime` (vLLM) + `InferenceService` serving Qwen3.6-27B (FP8) on
the single 24GB L4 (ADR-0019). A Day 1 component (ADR-0056). Depends on
`openshift_ai` (`DataScienceCluster` Ready) and `nvidia_gpu` (GPU
Operator) having run first.

`tasks/discover_vllm_image.yml` (ADR-0048) - included by `tasks/
install.yml` - discovers the vLLM serving-runtime image Red Hat
OpenShift AI actually published for this cluster/catalog instead of
trusting `gitops/charts/models/values.yaml`'s hardcoded fallback; see
that chart's own README for the full mechanism. `tasks/precheck.yml`
(state detection, never fails) does not run this discovery itself - it
only reports the `zuno-models-d0`/`zuno-models-d1` Applications'
Synced+Healthy status, setting `models_state_installed` and a line in the
shared `/tmp` state report (see `ansible/playbooks/day1_check.yml`). No
operator involved, so all of this component's content is `-d1` -
`zuno-models-d0` is a no-op (see `gitops/apps/README.md`).
