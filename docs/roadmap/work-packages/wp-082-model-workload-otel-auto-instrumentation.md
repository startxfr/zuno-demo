# WP-082: OTel auto-instrumentation for the model-serving workloads

- **State:** Done (live-verified 2026-08-26 on embeddings + qwen; gpt-oss-20b blocked on a
  pre-existing GPU-node capacity problem, see "Live finding: rollout deadlock" below).
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

## Live finding: any GPU-workload spec change deadlocks its own rollout

Not caused by this WP, but it blocks every rollout of these three workloads and cost most of
this WP's time, so it is recorded here. The `zuno-ai-run-gpu-cap` ResourceQuota caps MIG slices
at exactly the number in steady-state use (`mig-1g.24gb: 2`, `mig-2g.48gb: 1`), while the
KServe-generated Deployments use `RollingUpdate` with 25%/25% - at `replicas: 1` that rounds to
`maxSurge 1, maxUnavailable 0`. So the new ReplicaSet must create its pod *before* the old pod
is removed, but the quota is already fully consumed by that old pod:
`ReplicaFailure/FailedCreate: exceeded quota: zuno-ai-run-gpu-cap`, forever. The rollout is
silently stuck with `UPTODATE: 0` while `oc get pods` shows a healthy old pod. Deleting the old
pod (the WP-076 reflex) does NOT help - its own old ReplicaSet immediately recreates it.
**Escape used here: `oc scale rs <old-rs> --replicas=0`**, which frees the quota and lets the
new ReplicaSet create. A durable fix (e.g. `spec.predictor.deploymentStrategy: Recreate` on the
classic InferenceService - the field exists; LLMInferenceService has no equivalent) or raising
the quota by one slice per profile is NOT attempted here - it needs its own WP and a decision
about GPU headroom.

Compounding, pre-existing and unrelated to this WP: the single GPU node has been CPU-saturated
since ~08:40 on 2026-08-26 (13676m/88% requested, ~8.9 cores of non-model workload), so only
ONE of the two 4-core LLMs can be scheduled at a time - qwen and gpt-oss-20b have been trading
the node ever since, whichever is (re)created first. qwen won here; **`gpt-oss-20b` is
therefore `Pending` with the correct new spec but never scheduled**, and its half of item 3 is
unverified. Its spec is identical in shape to qwen's (same `spec.annotations` path, same args
block), so the risk is scheduling, not correctness.

## Verification checklist

1. ✅ Pre-checks: `oc explain instrumentation.spec.exporter/.sampler/.propagators` run before
   authoring the CR; `--otlp-traces-endpoint` confirmed present on the embeddings pod's vLLM
   build too (via `vllm serve --help=all` - hidden from plain `--help`).
2. ✅ Both KServe annotation-propagation paths proven live, and the webhook injected on both:
   - embeddings (`spec.predictor.annotations`, the previously-unproven classic-InferenceService
     path): pod carries both annotations, `kserve-container` has 10 `OTEL_*` vars
     (`OTEL_SERVICE_NAME=embeddings-predictor`, endpoint = platform collector,
     `OTEL_TRACES_SAMPLER=traceidratio`, `OTEL_PROPAGATORS=tracecontext,baggage`).
   - qwen (`spec.annotations`): same 10 vars in `main`
     (`OTEL_SERVICE_NAME=qwen36-27b-instruct-kserve`) **plus** the
     `--otlp-traces-endpoint=...` arg on the vLLM command line, echoed back by vLLM's own
     startup `ObservabilityConfig(otlp_traces_endpoint='http://zuno-otel-collector-collector...')`.
3. ✅ Real inference (HTTPS `POST /v1/chat/completions` on qwen, HTTP 200 - note the endpoint is
   TLS, KServe's own cert) produced **vLLM in-process spans** searchable in RHOAI's Tempo:
   `tags=service.name=qwen36-27b-instruct-kserve` → traces named `llm_request` (plus an
   `Overall Loading` model-load span). Tempo's `service.name` tag-values list now includes
   `qwen36-27b-instruct-kserve` and `isvc.embeddings-predictor.zuno-ai-run`.
   ⬜ gpt-oss-20b half: not verified, see the capacity finding above.
4. ✅ Dual-stack confirmed: the same `llm_request` traces are also in `zuno-monitoring`'s Tempo
   (`tempo-tempo:3200`), i.e. WP-081's fan-out delivers workload spans to both backends.

## Status updates

- WP-082 → Done (live-verified 2026-08-26), with the gpt-oss-20b scheduling caveat above.
- ADR-0523 → `Implemented`: both paths (mesh-level WP-081, workload-level WP-082) are live and
  trace data is landing in RHOAI's Tempo from real traffic. `docs/adr/README.md` row updated.
