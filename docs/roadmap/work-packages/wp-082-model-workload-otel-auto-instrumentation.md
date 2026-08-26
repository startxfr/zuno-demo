# WP-082: OTel auto-instrumentation for the model-serving workloads

- **State:** In progress (pushed, awaiting rollout + live verification).
- **ADRs:** ADR-0523 (To be implemented)
- **Depends on:** WP-079 (RHOAI traces stack live), WP-080 (diagnosed the zero-traces root causes)
- **Related:** WP-081 (mesh-level path, independent), WP-076/ADR-0521 (proved the
  `LLMInferenceService` `spec.annotations` pod-template propagation path this reuses)

## Goal

Make in-process KServe/vLLM spans reach RHOAI's Tempo. Ship a repo-owned `Instrumentation` CR
(`zuno-models-instrumentation`, `zuno-ai-run`) pointing at the **platform** collector
(`zuno-otel-collector-collector.zuno-monitoring.svc.cluster.local:4317`), whose WP-081 fan-out
carries a copy to RHOAI's Tempo with the gateway auth an in-process SDK cannot do - both Tempo
stacks get the workload spans. Deliberately NOT RHOAI's own collector: its
`data-science-instrumentation` names a Service that does not exist AND its Tempo export dials
a port the gateway never exposes, unfixable in place (see ADR-0523 and WP-081). Referenced from
all three model workloads via `instrumentation.opentelemetry.io/inject-sdk` pod annotations:

- `llminferenceservice-qwen.yaml` / `llminferenceservice-gptoss.yaml` via the existing
  `podAnnotations` values keys (`spec.annotations` propagation, live-proven by WP-076), plus
  vLLM's native `--otlp-traces-endpoint` flag (the injected env alone does not activate vLLM
  tracing; the flag is fed from values, not the injected env, because the webhook's
  `failurePolicy: Ignore` can silently skip injection and startup must not depend on it).
- `inferenceservice-embedding.yaml` via a new `spec.predictor.annotations` block (classic
  KServe v1beta1; propagation unverified in this repo - the checklist covers it). Annotation
  only, no vLLM flag initially: pooling/embed-request tracing support on this vLLM build is
  unverified; pre-check `vllm serve --help | grep -i otlp` in the running container and record
  the outcome here.

`inject-sdk`, not `inject-python`: the RH vLLM image ships opentelemetry-sdk 1.43.0 +
`opentelemetry-semantic-conventions-ai` (verified in the running qwen pod); env-only injection
carries zero runtime risk on GPU pods, where a `PYTHONPATH` sitecustomize shadowing the image's
newer SDK does not.

## What changed

- New `gitops/charts/models/templates/instrumentation.yaml`: `zuno-models-instrumentation`
  (`zuno-ai-run`, sync-wave -5), endpoint = the platform collector (see Goal),
  `traceidratio`/`"1.0"` sampler (mirrors RHOAI's `sampleRatio` and the mesh Telemetry CR's
  100%), `tracecontext`+`baggage` propagators. Fields checked via `oc explain` first.
- `gitops/charts/models/values.yaml`: new top-level `tracing:` block (`enabled`,
  `exporterEndpoint`); `inject-sdk` + `container-names` annotations added to qwen's
  `llmInferenceService.podAnnotations`, gptoss's `gptOssModel.llmInferenceService.podAnnotations`
  (`main`), and a new `embeddingModel.podAnnotations` key (`kserve-container`).
- `gitops/charts/models/templates/inferenceservice-embedding.yaml`: new
  `spec.predictor.annotations` block fed from `embeddingModel.podAnnotations`.
- `gitops/charts/models/templates/llminferenceservice-qwen.yaml` / `-gptoss.yaml`:
  `--otlp-traces-endpoint={{ tracing.exporterEndpoint }}` appended to the vLLM args, gated on
  `tracing.enabled`.
- Pre-check result: `--otlp-traces-endpoint` (and `--collect-detailed-traces`) confirmed
  present on the embeddings pod's vLLM build too (`vllm serve --help=all` - the flag is hidden
  from plain `--help`), so enabling the flag there later is a values-only follow-up once
  pooling-request span coverage is confirmed worthwhile.
- `helm template` verified: Instrumentation CR renders, embedding predictor annotations render,
  both LLM arg lists carry the flag; `tracing.enabled=false` renders everything back to the
  prior shape.

## Verification checklist

1. ⬜ Pre-checks: `oc explain instrumentation.spec.exporter/.sampler/.propagators` before
   authoring the CR; `vllm serve --help | grep -i otlp` in the embeddings kserve-container.
2. ⬜ After rollout, the qwen/gptoss workload pods and the embeddings predictor pod carry the
   `inject-sdk` annotation AND the operator-injected `OTEL_*` env in `main`/`kserve-container`
   (proves both KServe annotation propagation and webhook injection).
3. ⬜ A real chat/completions call through the MaaS gateway produces vLLM-originated spans in
   RHOAI's Tempo (search API, non-empty `traces` array with the model's service name).
4. ⬜ GPU rollout watched for the replicas=1/MIG-slice Pending deadlock (WP-076 precedent:
   delete the old pod if stuck).

## Status updates

_None yet._
