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

The chat model (`templates/llminferenceservice-qwen.yaml`, ADR-0521) and
the embedding model (`templates/inferenceservice-embedding.yaml`) both run
`minReplicas == maxReplicas == 1`/`replicas: 1`, always on, with no use for
Serverless's scale-to-zero. `openshift_ai`'s cluster-wide
`kserve.serving.managementState: Removed`
(`ansible/roles/openshift_ai/tasks/prepare.yml`) means neither model
requires the Service Mesh/Serverless operators plus cert-manager that
Serverless mode would need (none of which this repository installs); the
embedding model's classic `InferenceService` sets
`serving.kserve.io/deploymentMode: Standard` explicitly for the same
reason.

Depends on the `openshift_ai` role's `DataScienceCluster` having the
`kserve` component enabled, and the `nvidia_gpu` role's GPU Operator
(with `nfd` prepared first) being ready - all Day 0 components installed
before `models` (a Day 1 component) in `ansible/playbooks/day0_install.yml`.

## Chat model storage: S3, straight into the LLMInferenceService

Since 2026-08-18 the chat model's weights are staged in S3
(`s3://<modelsS3.bucket>/<modelsS3.prefix>/<servedModelName>/`, see
`values.yaml`'s `modelsS3` block - same bucket/credential as
rag-ingestion's corpus, `models/` prefix). `templates/llminferenceservice-
qwen.yaml`'s `spec.model.uri` reads straight from there, authenticated via
the `ServiceAccount` + `serving.kserve.io/s3-*`-annotated Secret from
`templates/s3-serving-credentials.yaml` - the same mechanism (and Vault
`rag/s3` credential) `templates/s3-serving-credentials-gptoss.yaml` uses
for gpt-oss-20b's own `LLMInferenceService`. KServe's storage-initializer
downloads ~15GB from same-region S3 onto the node at pod (re)start.

ADR-0521 removed the earlier HF→PVC predownload alternative
(`templates/pvc-model.yaml` + `templates/job-model-download.yaml`, gated
by a now-deleted `modelStorage.downloadJob.enabled` flag) along with the
classic `InferenceService`/`ServingRuntime` pair it backed: a classic
`InferenceService` can never get a `MaaSModelRef` (confirmed via `oc
explain maasmodelref.spec.modelRef.kind` - `LLMInferenceService` or
`ExternalModel` only), so the chat model had to become an
`LLMInferenceService` to ever be MaaS-published, same as gpt-oss-20b
before it (ADR-0414). The embedding model is unaffected - still its own
classic `InferenceService`/`ServingRuntime` pair, `storageUri: hf://`,
~130MB, no MaaS involvement.

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

**Adapter download is not wired up yet** - nothing in this chart moves a
registered adapter onto the pod's filesystem at the declared `path`. An
operator promoting an adapter today must also arrange for it to land
there (a follow-up PVC/init-container, deliberately out of this WP's own
~4-file scope) before it actually serves traffic.

**Classification gate**: `values.schema.json` and
`templates/llminferenceservice-qwen.yaml`'s own template-time `fail`
(ADR-0521 - formerly `templates/servingruntime.yaml`'s, before the chat
model's classic `InferenceService`/`ServingRuntime` pair was retired) both
reject any `loraAdapters[]` entry with `classification` other than `C1`
while `maas.enabled` is `true` (ADR-0201 publishes an
`LLMInferenceService` externally, making it an externally-eligible serving
path) - a C2/C3 adapter must never widen ADR-0021's C1/C2/C3 routing. Two
independent enforcements (schema + template) so the rule holds even for a
caller that renders this chart without schema validation.

`ansible/roles/models/tasks/precheck.yml` reads the declared adapter set
back off the `LLMInferenceService`'s own
`zuno.io/lora-adapter-classifications` annotation (never re-parsing
`values.yaml`, so it always agrees with what's actually deployed) and
queries the workload's `/v1/models` endpoint to report whether each one is
actually loaded - diagnostic only, UNVERIFIED against a live cluster (no
GPU/vLLM instance in this repo's sandbox to confirm the exact `/v1/models`
response shape with LoRA modules loaded).
