# ADR-0591: Route only to ready local models and fail fast on stalled candidates

- **Status:** Accepted
- **Target:** v0.13
- **Date:** 2026-11-02
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0560](0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md), [ADR-0570](0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md), [ADR-0567](0567-move-trustyai-guardrails-into-the-ai-gateway.md), [ADR-0544](0544-bound-every-model-call-at-both-ends.md), [ADR-0587](0587-admit-additional-user-experiences-over-the-one-governed-backend.md)

## Context

The ai-gateway walks an ordered list of candidates per classification (ADR-0560): for each local model a candidate
through MaaS (`*-maas`, ADR-0570) and a direct one, then the SaaS providers the classification allows. A failed
candidate hands over to the next one.

On 2026-11-02 the two GPU nodes of demo333 were `NotReady` and the four `LLMInferenceService` were `Ready=False`
(`MinimumReplicasUnavailable`). Measured from the gateway's own `zuno_model_call_duration_ms`:

- every direct local candidate failed in about 1.4 s (`Connection error`);
- every `*-maas` candidate failed after **180.1 s** (`Request timed out`), its configured timeout. MaaS never answered
  503: the model's llm-d router-scheduler was running and held the request waiting for a pod that would not come;
- a C1 chat from Open WebUI reached `openai` after about 10 minutes; claw-operator's proxy cuts at 300 s, so OpenClaw
  got a 500 before any SaaS provider was tried (WP-180, WP-182 evidence).

The 180 s timeout itself is deliberate (user decision 2026-10-31: qwen35-9b compiles JIT kernels during its first
inferences and ran past 60 s). It is right for a ready but slow model, and wrong for a model that is not there.

The same day the NeMo guardrails backend answered `unavailable` once: after its pod was rescheduled off the failed
GPU node, NeMo loaded its rails configuration on the first request (about 17 s), above the gateway's 10 s guardrails
timeout. Every later evaluation was clean. In `observe` mode the reply is unaffected; in `block` mode the same gap
would decide a request on a detector that never ran.

## Decision

**The ai-gateway skips a local model that its controller reports not ready, and a provider that just failed, instead
of waiting for each to time out.**

1. **Readiness.** The ai-gateway watches the `LLMInferenceService` objects of `zuno-ai-run` (read-only Role:
   get, list, watch) and treats a local model whose `Ready` condition is not `True` as unavailable. Each local
   provider of the routing table names its model explicitly (`inference_service:`); both candidates of a pair (direct
   and `*-maas`) are skipped together. No name is derived from an endpoint URL.
2. **Fail open on readiness.** If the watch is not established or the object is unknown, the model is treated as
   ready: today's behaviour, never a refusal caused by the readiness source itself.
3. **Circuit breaker per provider, per replica, as the safety net.** A candidate that fails by timeout, connection
   error or 5xx opens its breaker for a bounded time (default 60 s); while open the candidate is skipped; after it,
   one call is let through (half-open) and closes the breaker on success. A 429 (quota, ADR-0570), a 4xx and a
   guardrails refusal never open it. The breaker is in memory: no shared state, each replica learns on its own.
4. **No hidden retries on model calls.** Every model client runs with the SDK's own retries off
   (`max_retries=0`), MaaS and direct alike: the candidate loop is the only retry mechanism, so one failure costs one
   timeout.
5. **Timeouts unchanged.** 180 s on `*-maas`, 60 s direct (ADR-0544 and the decision of 2026-10-31). Readiness
   removes the absent models; the timeout keeps its meaning for slow ones.
6. **Fast, explicit refusal when nothing is left.** When every candidate the classification allows is skipped, the
   gateway answers 503 at once, with the reason (`not ready` or `circuit open`) per candidate, instead of waiting.
7. **Observable.** A counter `zuno_model_candidates_skipped{provider, reason}` (`not_ready`, `circuit_open`) and the
   reason on the `model_call` span; the routing decision of ADR-0550 records the skipped candidates.
8. **Guardrails warm-up.** The NeMo guardrails pod is not Ready until its rails configuration is loaded: a readiness
   check that runs one evaluation of the configured `config_id`, so the Service never routes to a cold NeMo. Where
   the operator does not let the pod template carry it, the ai-gateway runs one warm-up evaluation at its own start
   and after each `unavailable`. The gateway logs the exception type of an `unavailable`, never an empty message.
   *Update 2026-11-02:* the `NemoGuardrails` pod template carries no container probe, so the gateway path applies, and a
   warm-up at the gateway's start does not cover a NeMo pod restarted while the gateway runs. The warm-up therefore
   repeats every `GUARDRAILS_WARMUP_INTERVAL_SECONDS` (60): a restarted NeMo is warm again within one interval.

## Alternatives considered

- **Circuit breaker only:** no RBAC, local to the pod, but the first call after each breaker window still pays five
  times 180 s. Kept as the safety net (decision 3), not as the mechanism.
- **Probe the direct candidate before its `*-maas` twin:** a 1.4 s signal, but it either reverses the MaaS-first order
  that carries the budgets (ADR-0570) or adds a probe call to every request. Rejected.
- **A separate, shorter first-byte timeout:** would also cut a ready model's JIT warm-up, which is what the
  2026-10-31 decision protects. Rejected.
- **Back to 60 s on `*-maas`:** divides the worst case by three and reopens the qwen35-9b fallback. Rejected.
- **Raise the guardrails timeout:** hides the cold start and slows every real NeMo outage by the same amount. Rejected.

## Consequences

- The ai-gateway gains a Role and a watch on `llminferenceservices.serving.kserve.io`; its pods reach the API server.
- The routing table gains `inference_service:` on every local provider, in `platform/ai-gateway/provider-routing.yaml`
  and in the generated routing (`model-routing.generated.yaml`), so `check_docs.py`'s routing checks see it.
- With the GPU nodes down, a chat goes straight to the first eligible SaaS provider; a C3 or local-only request gets
  an immediate 503 instead of a timeout after many minutes.

## Security considerations

The Role is read-only and namespace-scoped. A skipped candidate never widens routing: the classification still
decides the eligible list, readiness and the breaker only remove entries from it. Fail-open on readiness keeps a
compromised or silent API from denying service, at the price of today's slow path.

## Operational considerations

`zuno_model_candidates_skipped` going up while models are `Ready` points at the breaker, not at the models; a model
that is `Ready` but always times out stays slow by design (decision 5) and is visible in the call duration.
