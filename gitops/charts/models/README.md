# models chart

KServe `ServingRuntime` (vLLM) + `InferenceService` for the demo's one local
model, Qwen2.5-7B-Instruct - sized to fit one 24GB NVIDIA L4 in fp16 with
headroom for KV cache at the demo's low concurrency (~5 concurrent
conversations, MEMORY.md). Serves an OpenAI-compatible `/v1` API, which is
what `components/agent-runtime`'s model router expects at
`agent-runtime.localModelEndpoint` / `localModelName`
(`gitops/charts/agent-runtime/values.yaml`).

## Serving runtime image discovery (ADR-0048)

`values.yaml`'s `image.vllm` is a `helm template`/standalone-testing
fallback only - it is never trusted for a real deploy. `ansible/roles/models`'s
`tasks/discover_vllm_image.yml` (included by both `tasks/precheck.yml` and
`tasks/install.yml`) discovers the actual vLLM serving-runtime image
Red Hat OpenShift AI published for the installed cluster/catalog, by
reading the `Template` objects in `zuno-ai-build` (the same
catalog the dashboard's "Serving runtimes" page reads from - `oc get
templates -n zuno-ai-build | grep -i vllm` is the manual
equivalent), and overrides this chart's default at apply time via the
ArgoCD Application's `spec.source.helm.values` (see
`ansible/tasks/apply_gitops_app.yml`'s `gitops_app_extra_helm_values`).
Fails with a clear diagnostic (listing the templates that *were* found) if
no vLLM template is published, rather than silently deploying the
`values.yaml` fallback. An operator who already knows the correct image
can bypass discovery entirely with
`-e models_vllm_image_override=<registry>/<image>:<tag>` - an explicit,
conscious override, never a silent one (ADR-0048 Security considerations).

## RawDeployment, not Serverless (ADR-0047)

`templates/inferenceservice.yaml` sets
`serving.kserve.io/deploymentMode: RawDeployment` explicitly, matching the
`openshift_ai` role's cluster-wide `kserve.serving.managementState: Removed`
(`ansible/roles/openshift_ai/tasks/prepare.yml`) - this model runs
`minReplicas == maxReplicas == 1`, always on, with no use for Serverless's
scale-to-zero, and RawDeployment avoids requiring the Service Mesh and
Serverless operators plus cert-manager that Serverless mode would
otherwise need (none of which this repository installs - see that role's
own comment for the full reasoning, this was a real, previously
undeclared dependency gap, not a hypothetical one).

Depends on the `openshift_ai` role's `DataScienceCluster` having the
`kserve` component enabled, and the `nvidia_gpu` role's GPU Operator (with
`nfd`, Node Feature Discovery, prepared first - ADR-0047) being ready -
all are Day 0 components (ADR-0056) installed before `models` (a Day 1
component) in `ansible/playbooks/day0_install.yml`.

## Second model: embeddings

`values.yaml`'s `embeddingModel.*` block plus `templates/servingruntime-embedding.yaml`,
`templates/inferenceservice-embedding.yaml` and `templates/networkpolicy-embedding.yaml`
add a second, additive vLLM `ServingRuntime`/`InferenceService`
(`granite-embedding`, `ibm-granite/granite-embedding-125m-english`,
768-dim) serving embeddings via vLLM's `--task embed` mode, reusing the
same `image.vllm` runtime image discovered for the chat model above -
kept additive rather than folding both models into a `models: []` list,
since only these two exist and a list-based rewrite would be a breaking
change to this chart's flat values shape for no benefit at this scale.

Consumed by `gitops/charts/rag-ingestion`'s `embedding.endpoint`
(fetch-time chunk embedding, from `zuno-ai-build`) and available to
`rag-service` for query-time embedding (from `zuno-data`) - both allowed
by `templates/networkpolicy-embedding.yaml`.
