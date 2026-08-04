# models chart

KServe `ServingRuntime` (vLLM) + `InferenceService` for the demo's one local
model, Qwen2.5-7B-Instruct — sized to fit one 24GB NVIDIA L4 in fp16 with
headroom for KV cache at the demo's low concurrency (~5 concurrent
conversations, MEMORY.md). Serves an OpenAI-compatible `/v1` API, which is
what `components/agent-runtime`'s model router expects at
`agent-runtime.localModelEndpoint` / `localModelName`
(`gitops/charts/agent-runtime/values.yaml`).

**ASSUMPTION** (not verified against a live cluster): `values.yaml`'s
`image.vllm` points at Red Hat OpenShift AI 3.5's bundled vLLM runtime image
tag as best-effort guess — confirm the exact tag published in the installed
RHOAI 3.5 EA2 catalog and update before a real deploy (`oc get
templates -n redhat-ods-applications | grep -i vllm` is a reasonable place
to start once a cluster is available).

Depends on the `openshift_ai` role's `DataScienceCluster` having the
`kserve` component enabled, and the `nvidia_gpu` role's GPU Operator being
ready — both are PREP_COMPONENTS applied before `models` in
`ansible/playbooks/{precheck,prepare}.yml`.
