# WP-082: OTel auto-instrumentation for the model-serving workloads

- **State:** Not started.
- **ADRs:** ADR-0523 (To be implemented)
- **Depends on:** WP-079 (RHOAI traces stack live), WP-080 (diagnosed the zero-traces root causes)
- **Related:** WP-081 (mesh-level path, independent), WP-076/ADR-0521 (proved the
  `LLMInferenceService` `spec.annotations` pod-template propagation path this reuses)

## Goal

Make in-process KServe/vLLM spans reach RHOAI's Tempo. Ship a repo-owned `Instrumentation` CR
(`zuno-models-instrumentation`, `zuno-ai-run`) pointing at the **corrected** collector endpoint
(`data-science-collector-collector.redhat-ods-monitoring.svc.cluster.local:4317` - RHOAI
3.5.0-ea.2's own `data-science-instrumentation` names a Service that does not exist, see
ADR-0523), and reference it from all three model workloads via
`instrumentation.opentelemetry.io/inject-sdk` pod annotations:

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

_To be filled during implementation._

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
