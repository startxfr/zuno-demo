# models chart

KServe `ServingRuntime` (vLLM) + `InferenceService` for the demo's one local
model, Qwen2.5-7B-Instruct - sized to fit one 24GB NVIDIA L4 in fp16 with
headroom for KV cache at the demo's low concurrency (~5 concurrent
conversations, MEMORY.md). Serves an OpenAI-compatible `/v1` API, which is
what `components/agent-runtime`'s model router expects at
`agent-runtime.localModelEndpoint` / `localModelName`
(`gitops/charts/agent-runtime/values.yaml`).

## Serving runtime image discovery

`values.yaml`'s `image.vllm` is a `helm template`/standalone-testing
fallback only - never trusted for a real deploy. `ansible/roles/models`'s
`tasks/discover_vllm_image.yml` (included by `tasks/precheck.yml` and
`tasks/install.yml`) discovers the actual vLLM serving-runtime image
RHOAI published for the installed cluster/catalog, by reading `Template`
objects in `redhat-ods-applications` (`oc get
templates -n redhat-ods-applications | grep -i vllm` is the manual
equivalent), preferring the CUDA-flavored template since this chart
requests `nvidia.com/gpu`, and overrides this chart's default at apply
time via the ArgoCD Application's `spec.source.helm.values` (see
`ansible/tasks/apply_gitops_app.yml`'s `gitops_app_extra_helm_values`).
Fails with a diagnostic (listing found templates) rather than silently
deploying the `values.yaml` fallback; bypass discovery entirely with
`-e models_vllm_image_override=<registry>/<image>:<tag>`.

## RawDeployment, not Serverless

`templates/inferenceservice.yaml` sets
`serving.kserve.io/deploymentMode: Standard` explicitly, matching the
`openshift_ai` role's cluster-wide `kserve.serving.managementState: Removed`
(`ansible/roles/openshift_ai/tasks/prepare.yml`) - this model runs
`minReplicas == maxReplicas == 1`, always on, with no use for Serverless's
scale-to-zero, and RawDeployment avoids requiring the Service Mesh/
Serverless operators plus cert-manager that Serverless mode would need
(none of which this repository installs).

Depends on the `openshift_ai` role's `DataScienceCluster` having the
`kserve` component enabled, and the `nvidia_gpu` role's GPU Operator
(with `nfd` prepared first) being ready - all Day 0 components installed
before `models` (a Day 1 component) in `ansible/playbooks/day0_install.yml`.

## Chat model storage: PVC, not the node's ephemeral disk

`templates/pvc-model.yaml` + `templates/job-model-download.yaml` predownload
the chat model into a PVC once, instead of `storageUri: hf://` (still used
by the embedding model), which downloads straight into the GPU node's
ephemeral root disk on every pod (re)start. The node's 75GB root volume
can't hold the CUDA vLLM image (17.67GB) + a fresh ~15GB `hf://` download +
NVIDIA driver build artifacts (~7GB) at once.
`templates/inferenceservice.yaml`'s `storageUri: pvc://...` then has KServe
mount that PVC directly, with no download/storage-initializer step at pod
start.

The PVC and the download Job are both plain sync-wave resources (PVC wave
-20, Job wave -15, before the ServingRuntime's -5), not ArgoCD `PreSync`
hooks - hooks would make ArgoCD delete and recreate the PVC (and its
~15GB downloaded model) on every resync. As plain, wave-ordered resources,
ArgoCD only touches either object again when its own spec actually
changes; the Job's pod, one wave later, is still `gp3-csi`'s first
consumer, so `WaitForFirstConsumer` binding still works.

Both the Job and the `InferenceService`'s predictor carry the same
`nodeSelector: topology.kubernetes.io/zone: {{ .Values.modelStorage.zone }}`:
`gp3-csi` is single-AZ (EBS), so the PVC only mounts on nodes in the zone it
bound in. This demo's GPU nodes currently span two zones -
`values.yaml`'s `modelStorage.zone` pins both to the same one. Adding more
GPU nodes for this model must keep them in that zone, or this needs
per-zone PVCs/affinity instead of one shared value.

## Second model: embeddings

`values.yaml`'s `embeddingModel.*` block plus `templates/servingruntime-embedding.yaml`,
`templates/inferenceservice-embedding.yaml` and `templates/networkpolicy-embedding.yaml`
add a second, additive vLLM `ServingRuntime`/`InferenceService`
(`granite-embedding`, `ibm-granite/granite-embedding-125m-english`,
768-dim) serving embeddings via vLLM's `--task embed` mode, reusing the
same `image.vllm` runtime image discovered for the chat model above.
Requests `nvidia.com/gpu` like the chat model: the discovered/pinned
`image.vllm` is a CUDA-only build, which crashes with "Failed to infer
device type" if scheduled without a GPU. Has no `nodeSelector` of its own
(unlike the chat model above), so it's free to land on whichever GPU node
still has a free GPU.

Consumed by `gitops/charts/rag-ingestion`'s `embedding.endpoint`
(fetch-time chunk embedding, from `zuno-ai-build`) and available to
`rag-service` for query-time embedding (from `zuno-data`) - both allowed
by `templates/networkpolicy-embedding.yaml`.
