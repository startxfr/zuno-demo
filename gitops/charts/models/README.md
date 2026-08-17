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
requests GPU capacity (`nvidia.com/mig-*` slices since ADR-0351), and
overrides this chart's default at apply
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
`nodeSelector: nvidia.com/gpu.present: "true"` - not a specific zone.
`gp3-csi` is single-AZ (EBS), so the PVC only mounts on nodes in the zone it
bound in, but since `WaitForFirstConsumer` delays binding until the Job's
pod is actually scheduled, the PVC always ends up bound in whichever zone
that GPU node happens to be in - and the predictor, requiring a GPU node
too, is then implicitly constrained to a matching node by the bound PV's
own node-affinity. Neither template needs to know the zone name, and this
keeps working unchanged as GPU nodes are added in other zones. (An earlier
version of this chart hardcoded a zone value here - see `values.yaml`'s
`modelStorage` comment for why that broke the moment the demo's GPU
topology changed.)

## Second model: embeddings

`values.yaml`'s `embeddingModel.*` block plus `templates/servingruntime-embedding.yaml`,
`templates/inferenceservice-embedding.yaml` and `templates/networkpolicy-embedding.yaml`
add a second, additive vLLM `ServingRuntime`/`InferenceService`
(`granite-embedding`, `ibm-granite/granite-embedding-125m-english`,
768-dim) serving embeddings via vLLM's `--task embed` mode, reusing the
same `image.vllm` runtime image discovered for the chat model above.
Requests GPU capacity like the chat model - a `nvidia.com/mig-1g.24gb`
slice since ADR-0351, vs the chat model's `mig-2g.48gb`: the
discovered/pinned `image.vllm` is a CUDA-only build, which crashes with
"Failed to infer device type" if scheduled without a GPU. Has no
`nodeSelector` of its own (unlike the chat model above), so it's free to
land on whichever MIG-partitioned node has a free 24GB slice - by design
the same permanent node as the chat model (the old full-GPU-era hard
anti-affinity between the two was removed by ADR-0351).

Consumed by `gitops/charts/rag-ingestion`'s `embedding.endpoint`
(fetch-time chunk embedding, from `zuno-ai-build`) and available to
`rag-service` for query-time embedding (from `zuno-data`) - both allowed
by `templates/networkpolicy-embedding.yaml`.

## LoRA adapter serving (ADR-0301, WP-34 Part B)

`values.yaml`'s `loraAdapters` list is additive and default-empty:
vLLM's native multi-LoRA support (`--enable-lora`/`--lora-modules`) on
the SAME chat-model `ServingRuntime`/`InferenceService` above, never a
second deployment per adapter (ADR-0301 point 1). Each entry names the
OpenShift AI Model Registry model/version it came from
(`components/mlops`'s `push-registry` stage, ADR-0302 point 6), the
filesystem `path` vLLM reads it from, and its inherited classification
(ADR-0301 point 4). Which adapter (if any) actually applies to a given
request is static config here - dynamic, per-request selection is
ADR-0303/WP-39's own scope, not this chart's.

**Adapter download is not wired up yet** - unlike the chat model's own
PVC + `job-model-download.yaml` predownload, nothing in this chart moves
a registered adapter onto the pod's filesystem at the declared `path`.
An operator promoting an adapter today must also arrange for it to land
there (a follow-up PVC/init-container, deliberately out of this WP's own
~4-file scope) before it actually serves traffic.

**Classification gate**: `values.schema.json` and
`templates/servingruntime.yaml`'s own template-time `fail` both reject
any `loraAdapters[]` entry with `classification` other than `C1` while
`maas.enabled` is `true` (ADR-0201 publishes this same InferenceService
externally, making it an externally-eligible serving path) - a C2/C3
adapter must never widen ADR-0021's C1/C2/C3 routing. Two independent
enforcements (schema + template) so the rule holds even for a caller that
renders this chart without schema validation.

`ansible/roles/models/tasks/precheck.yml` reads the declared adapter set
back off the ServingRuntime's own `zuno.io/lora-adapter-classifications`
annotation (never re-parsing `values.yaml`, so it always agrees with
what's actually deployed) and queries the predictor's `/v1/models`
endpoint to report whether each one is actually loaded - diagnostic only,
UNVERIFIED against a live cluster (no GPU/vLLM instance in this repo's
sandbox to confirm the exact `/v1/models` response shape with LoRA
modules loaded).
