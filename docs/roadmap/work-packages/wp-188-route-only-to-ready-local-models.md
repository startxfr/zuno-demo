# WP-188: Route only to ready local models and fail fast on stalled candidates

- **State:** Repo work in review (steps 1 to 6 in the repository, 2026-11-02; step 7 is live and waits for the user's go)
- **ADRs:** [ADR-0591](../../adr/0591-route-only-to-ready-local-models-and-fail-fast-on-stalled-candidates.md)
- **Depends on:** [WP-179](wp-179-common-preparation-for-experience-clients.md)
- **Related:** [WP-180](wp-180-open-webui-preparation.md), [WP-182](wp-182-openclaw-preparation.md)
- **Target:** v0.13
- **Estimated files touched:** ~12 in `zuno-demo` (`components/ai-gateway` app and tests, `gitops/charts/ai-gateway` Role and
  values, `platform/ai-gateway/provider-routing.yaml`, the routing generator, `gitops/charts/trustyai-config` NeMo template, docs)

> Decisions of 2026-11-02 (user): readiness from the `LLMInferenceService` controller plus a per-provider circuit breaker; the
> 180 s `*-maas` timeout stays; the NeMo warm-up is part of this package; recorded as ADR-0591.

## Goal

With a local model down, a request reaches the next eligible candidate in seconds, not after one 180 s timeout per
`*-maas` candidate; with every eligible candidate down, the caller gets a 503 at once. A restarted NeMo never answers its
first evaluation `unavailable`.

## What was measured (demo333, 2026-11-02)

- GPU nodes `NotReady`; `gpt-oss-20b`, `qwen35-9b`, `qwen35-9b-wesh`, `qwen36-27b-instruct` `Ready=False`
  (`MinimumReplicasUnavailable`), their `*-kserve-router-scheduler` pods Running.
- Mean `zuno_model_call_duration_ms` on errors: direct locals 1.3 to 1.4 s (`Connection error`), `*-maas` 180.1 s
  (`Request timed out`); `openai` success 1.3 s. A C1 chat reached `openai` after about 10 minutes.
- The MaaS client already runs with `max_retries=0` when the 429 pass-through is on (`app/maas_adapter.py`); the direct local
  clients (`app/providers.py`) keep the SDK default.
- NeMo (`zuno-guardrails`, owned by the `NemoGuardrails` CR) logged `Registered Actions` once, about 17 s after the first
  request of its new pod; the ai-gateway gave up at 10 s with an empty exception message. Its readiness probe is a `GET /`.

## Steps

1. **Routing table.** `inference_service: <LLMInferenceService name>` on every local provider of
   `platform/ai-gateway/provider-routing.yaml` (both members of each pair) and in `platform/okf/generate_stack_config.py`'s
   output; `check_docs.py`'s model-role check requires it on `kind: local` providers.
2. **Readiness watcher** (`components/ai-gateway/app/model_readiness.py`): a watch on `llminferenceservices` in the
   gateway's namespace with the pod's ServiceAccount, the `Ready` condition cached per name; unknown or no watch means
   ready (ADR-0591 decision 2). Chart: `templates/role.yaml` (get, list, watch on
   `llminferenceservices.serving.kserve.io`), RoleBinding to the gateway's ServiceAccount, and the API server reachable
   from the pod (check the egress of `zuno-ai-run` and the mesh first).
3. **Circuit breaker** (`components/ai-gateway/app/circuit_breaker.py`): per provider, opened by timeout, connection error
   or 5xx, never by 429, 4xx or a guardrails refusal; `open_seconds` from values (default 60); half-open lets one call
   through.
4. **Candidate loop** (`app/main.py`, both the streaming and non-streaming paths): skip not-ready and open candidates before
   calling them, record `zuno_model_candidates_skipped{provider,reason}` and the reason on the span and in the routing
   decision; answer 503 with the per-candidate reasons when nothing is left. `max_retries=0` on every model client.
5. **NeMo warm-up.** `oc explain nemoguardrails.spec.template` first. If the template accepts a container probe: a
   readiness `exec` probe that posts one evaluation of `configId` to `localhost:8000` (no curl in the image is assumed:
   check what the image carries). Otherwise: the ai-gateway runs one warm-up evaluation at start and after each
   `unavailable`. In both cases `app/guardrails.py` logs the exception type of an `unavailable`.
6. **Tests.** Unit: readiness cache and fail-open, breaker transitions, the loop skipping and the immediate 503, 429 not
   opening the breaker, `max_retries=0` on every client. The suite stays at 300/300 plus the new tests.
7. **Live, after the user's go** (shared ai-gateway: announce to the other sessions first). Build with `-e day1_verb=build`,
   roll, then with the GPU nodes still down: a C1 chat answers from the first SaaS provider in seconds, a local-only
   request gets an immediate 503, `zuno_model_candidates_skipped{reason="not_ready"}` counts the pairs. Restart the NeMo pod:
   its first evaluation through the gateway is `clean`, not `unavailable`. When the GPU nodes come back: the models
   are used again without a gateway restart.

## Implementation notes (2026-11-02)

- **Step 1.** `inference_service:` on the eight local providers (four pairs), each checked against its endpoint;
  `check_docs.py`'s model-role check now requires it on `kind: local`. `generate_stack_config.py` is not touched: it reads
  `provider-routing.yaml` for the MaaS subscriptions only, and an extra key is ignored there.
- **Step 2.** `app/model_readiness.py` polls (every 10 s, no watch) `serving.kserve.io/v1alpha2` LLMInferenceService objects
  with the existing projected token (`/var/run/secrets/maas/token`, audience `https://kubernetes.default.svc`); the pod's
  default ServiceAccount mount stays off. CA from the `kube-root-ca.crt` ConfigMap. Fails open: never polled, stale after
  three polls, unknown object, or switched off. Chart: `templates/role-model-readiness.yaml` (Role + RoleBinding, get, list,
  watch), values `availability.readiness`, passed by the `llm` role (`zuno_ai_gateway_model_readiness`, default false).
- **Step 3.** `app/circuit_breaker.py`: opened by timeout, connection error or 5xx; a 429 or any 4xx closes it (the provider
  answered); one half-open trial after `openSeconds` (60), and a trial that never reports back expires after the same window.
  Values `availability.circuitBreaker`, role variable `zuno_ai_gateway_circuit_breaker`, default false.
- **Step 4.** Both candidate loops skip `not_ready` and `circuit_open` after every policy skip, count
  `zuno_model_candidates_skipped{provider,reason,client}`, and record success or failure on the breaker.
  `chat_completions` answers 503 with the per-candidate reasons before a stream starts when nothing is available (the breaker
  is peeked, so the loop still gets its trial); the non-streaming loop answers 503 instead of 502 when every entry was an
  availability skip. `max_retries=0` on the seven direct clients and, always, on MaaS (it was only with the 429 pass-through).
- **Step 5.** `oc explain nemoguardrails.spec.template`: only pod-level scheduling, no container probe. So the ai-gateway warms
  NeMo up itself: one evaluation with `GUARDRAILS_WARMUP_TIMEOUT_SECONDS` (60) at start and after each `unavailable`, in the
  background, recording no metric. An `unavailable` now logs the exception type.
- **Step 6.** `tests/test_wp188_availability.py` (13), including the `local_only_for` case asked by the agents-routing
  session: with no ready local model, a local-only request ends in 503 and never reaches a SaaS provider.
  `test_wp157_maas_switches.py` now expects `max_retries=0` without the pass-through. Suite 313/313.
- **Rollout order (step 7).** Push (the ai-gateway pod rolls once for the new `GUARDRAILS_WARMUP_TIMEOUT_SECONDS`, still on
  the old image; the mounted routing gains a key the current loader ignores), build with `-e day1_verb=build`, then set
  `zuno_ai_gateway_model_readiness: true` and `zuno_ai_gateway_circuit_breaker: true` in `ansible/clusters/demo333.yml` and
  apply the `llm` role.

## Acceptance

With every local model `Ready=False`, a C1 chat through the ai-gateway answers in under 10 s from a SaaS provider and a
local-only request gets a 503 in under 2 s, with the skipped candidates visible in raw Prometheus; with the models back,
local candidates serve again; a freshly restarted NeMo answers its first evaluation.
