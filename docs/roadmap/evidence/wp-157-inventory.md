# WP-157 inventory: providers, quota rules and the plan for steps 3-5 (2026-10-24)

Read-only inventory for [WP-157](../work-packages/wp-157-slim-the-ai-gateway-via-maas.md)
step 2, under [ADR-0570](../../adr/0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md).
Taken on `devel` at `025d41c0`. The corp quota policy was read from the admitted
zuno-demo-agents release v0.3.0 (`platform/okf/agents.lock`,
`quay.io/zuno/okf-corp@sha256:83bd19e0...`), extracted by
`platform/okf/release_cache.py`; its lines are cited as `quota-policy.yaml:N`.
CRD field names come from `oc explain` output captured read-only on demo333
(no cluster was touched to write this). Nothing was modified except this file
and one link in the WP-157 brief. Line numbers drift: re-grep before editing.

## Findings that change the plan

1. **No quota class other than `standard` is ever selected in practice.** No
   bundle in release v0.3.0 declares `zuno.quota_class` or
   `zuno.limits.quota_class` (a grep of the release's `agents/` finds only
   prose), and UnifAI does not send `X-Zuno-Quota-Class` or
   `X-Zuno-Project-Id` until WP-146 settles how they are verified
   (ADR-0563 clause 5, `docs/adr/0563-*.md:106-114`). The gateway defaults the
   class to `standard` (`components/ai-gateway/app/main.py:317,339`). Only the
   Day 3 probe `platform/testing/token_quota_429.py:6-13` sends
   `stresstest`. So the project dimension and the `intensive` class are inert
   today for real traffic.
2. **`fail_mode` is never read at runtime.** `TokenBudgetLedger.fail_open()`
   (`app/quota.py:173-176`) has no caller in `app/` (grep). With a missing or
   broken `quota_budgets.yaml`, `check()` denies every class, `standard`
   included (`app/quota.py:138-143`), contrary to the module docstring
   (`app/quota.py:29-32`). ADR-0570 clause 7 needs `fail_mode` at runtime, so
   it is new code, not a reuse.
3. **`precedence` and `project_binding` in `quota_budgets.yaml` are not read
   either.** The order is hard-coded in `check()`/`consume()`
   (`app/quota.py:144-171`); the YAML keys (`quota_budgets.yaml:43-52`) are
   informative only.
4. **A MaaS 429 would today be treated as a provider failure.** Both candidate
   loops catch every exception and try the next candidate
   (`app/main.py:759-765`, `app/main.py:984-991`), so a quota 429 from MaaS
   would fall through to the direct sibling (bypassing quota) and then to SaaS.
   The final error is a 502 (`app/main.py:834-837`), not a 429.
   `chat_model_via_maas` sets no `max_retries` (`app/maas_adapter.py:198-213`),
   so the openai client's own retry policy applies to 429s (SDK default; check
   the pinned version).
5. **MaaS token limits are per model and per selected subscription.**
   `tokenRateLimits` sits under each `spec.modelRefs[]` entry of a
   `MaaSSubscription` (live CRD: `modelRefs[].tokenRateLimits[].{limit,window}`),
   and maas-api's selector returns one subscription per request
   (`docs/roadmap/evidence/maas-llm-path-identity-off-by-one.md:83-91`).
   ADR-0511 budgets span every provider (one counter per user/group/project
   across all models, `app/quota.py:92-115`). A cross-model budget therefore
   cannot be a `MaaSSubscription`; it needs a `TokenRateLimitPolicy` whose
   counters do not include the model.
6. **The existing SaaS subscriptions contradict ADR-0570's security rule.**
   `mistral-large-maas` and `gpt-oss-120b-ovhcloud-maas` grant `/agent_tekos`
   and `/sales` (`gitops/charts/models/values.yaml:1215-1226,1247-1258`), while
   ADR-0570 grants SaaS subscriptions only to groups limited to C1 content.
   Tekos handles C2 work. If the gateway keeps forwarding the caller's token
   (`app/maas_adapter.py:100-101`), each persona needs a SaaS subscription and
   can then call the SaaS model through MaaS without Zuno's classification
   (ADR-0570 clause 5 path). See decision D5.
7. **Forwarded Keycloak tokens: the record contradicts itself.** WP-122 records
   a persona token getting 200 through `local-wesh-maas` on 2026-09-03
   (`docs/roadmap/work-packages/wp-122-*.md:3-6`);
   `platform/testing/token_quota_429.py:22-37` records a persona token getting
   401 from MaaS on 2026-09-09 with no OIDC rule in `maas-gateway-auth`. On a
   fresh RHOAI 3.5.0 GA cluster the `ModelsAsService` CR carrying
   `externalOIDC` is not rendered at all (`gitops/charts/models/templates/maas.yaml:70-84`).
8. **Credentials stay in the gateway's namespace.** `ExternalModel`s and their
   mirror Secrets render in `.Values.namespace` = `zuno-ai-run`
   (`gitops/charts/models/values.yaml:4`,
   `templates/externalmodel-mistral.yaml:19,43`), which is also the
   ai-gateway's namespace (`platform/ai-gateway/kustomization.yaml:14`,
   `gitops/charts/ai-gateway/values.yaml:1`). "Keys leave the gateway"
   (ADR-0570 clause 4) means leaving the pod's env, not the namespace.
9. **The image endpoint has no quota check.** `/v1/images/generations`
   (`app/main.py:504-551`) never calls `quota.ledger`.

## 1. Providers

Sources: `platform/ai-gateway/provider-routing.yaml` (chat),
`platform/ai-gateway/image-provider-routing.yaml` (image). "Key today" is the
env var named by `api_key_env`, filled by `gitops/charts/ai-gateway/templates/deployment.yaml`
from `providerSecrets` (`gitops/charts/ai-gateway/values.yaml:71-80`), each a
Secret created by `platform/ai-gateway/externalsecret-<p>.yaml` from Vault
`providers/<p>` property `api_key` via `ClusterSecretStore vault-backend`.

| # | Provider (file:line) | Kind / role | API format | Reached today | Key today | Target MaaS construct | Verified? |
|---|---|---|---|---|---|---|---|
| 1 | `local-maas` qwen3.6-27b-instruct (`provider-routing.yaml:179-189`) | local / quality | OpenAI chat (vLLM) | via_maas, `maas-default-gateway-istio.../zuno-ai-run/qwen36-27b-instruct/v1` (`:186`); `providers.py:83-95` | caller's Keycloak token, else SA token `MAAS_SA_TOKEN_PATH` (`maas_adapter.py:78-107`) | existing LLMInferenceService `qwen36-27b-instruct` + MaaSModelRef `qwen36-27b-instruct-maas` (`models/values.yaml:1069-1118`) | yes 2026-08-26 (`adr-0521-maas-local-traffic.md:141-151`); regressed: instant 503 then 403 on demo333 2026-10-24 (`maas-front-wasm-not-loaded-2026-10-24.md`) |
| 2 | `local` (`:196-206`) | local / quality, `serves_adapters` | OpenAI chat (vLLM) | direct `qwen36-27b-instruct-kserve-workload-svc:8000` (`providers.py:97-143`) | none (`LOCAL_MODEL_API_KEY`, default `not-required`, `providers.py:127`) | stays direct: ADR-0570 clause 7 sibling (open classes only) and the only LoRA path (`main.py:554-572`) | yes (in service) |
| 3 | `local-gpt-oss-maas` gpt-oss-20b (`:240-250`) | local / reasoning | OpenAI chat | via_maas (`:247`) | as #1 | existing LLMInferenceService `gpt-oss-20b` + MaaSModelRef `gpt-oss-20b-maas` (`models/values.yaml:967-1061`) | yes 2026-08-26 (same evidence); same 2026-10-24 regression |
| 4 | `local-gpt-oss` (`:252-260`) | local / reasoning | OpenAI chat | direct workload Service | none | stays direct (clause 7 sibling) | yes |
| 5 | `local-wesh-maas` qwen3.5-9b-wesh (`:289-299`) | local / specialized | OpenAI chat | via_maas (`:296`) | as #1 | existing LLMInferenceService `qwen35-9b-wesh` + MaaSModelRef `qwen35-9b-wesh-maas` (`models/values.yaml:1128-1160`) | yes 2026-09-03 with a persona token (WP-122); see finding 7 |
| 6 | `local-wesh` (`:301-309`) | local / specialized | OpenAI chat | direct | none | stays direct (clause 7 sibling) | yes |
| 7 | `local-qwen35-maas` qwen3.5-9b (`:320-330`) | local / default | OpenAI chat | via_maas (`:327`) | as #1 | existing LLMInferenceService `qwen35-9b` + MaaSModelRef `qwen35-9b-maas` (`models/values.yaml:1169-1201`) | to verify live (no dedicated record found); 2026-10-24 regression applies |
| 8 | `local-qwen35` (`:332-340`) | local / default | OpenAI chat | direct | none | stays direct (clause 7 sibling) | yes |
| 9 | `openai` gpt-4o-mini (`:342-348`) | saas / general-external, C1-C2 | OpenAI chat | direct, `ChatOpenAI` default base URL (`providers.py:145-154`) | `OPENAI_API_KEY` <- `llm-provider-openai` (`deployment.yaml:101-106`, `externalsecret-openai.yaml:10,24`) <- Vault `providers/openai` | new ExternalModel, `provider` candidate `openai` (else `openai-compatible`), endpoint `api.openai.com`, `credentialRef` `llm-provider-openai-maas` (key `api-key`) | to verify live |
| 10 | `gemini` gemini-1.5-pro (`:350-356`) | saas / general-external, C1 | Gemini native (`ChatGoogleGenerativeAI`, `providers.py:155-166`) | direct | `GEMINI_API_KEY` <- `llm-provider-gemini` (`deployment.yaml:107-112`) <- `providers/gemini` | new ExternalModel, `provider` candidate `gemini`/`google` (no enum), endpoint `generativelanguage.googleapis.com`; fallback option: Google's OpenAI-compatible endpoint with `openai-compatible`; `credentialRef` `llm-provider-gemini-maas` | to verify live |
| 11 | `anthropic` claude-3-5-sonnet-latest (`:358-364`) | saas / general-external, C1-C2 | Anthropic Messages native (`ChatAnthropic`, `providers.py:167-179`) | direct | `ANTHROPIC_API_KEY` <- `llm-provider-anthropic` (`deployment.yaml:113-118`) <- `providers/anthropic` | new ExternalModel, `provider` candidate `anthropic` (the CRD description names Anthropic as an example), endpoint `api.anthropic.com`; fallback option: Anthropic's OpenAI-SDK-compatible endpoint with `openai-compatible`; `credentialRef` `llm-provider-anthropic-maas` | to verify live |
| 12 | `mistral` mistral-large-latest (`:366-372`) | saas / general-external, C1 | Mistral native (`ChatMistralAI`, `providers.py:180-188`) | direct | `MISTRAL_API_KEY` <- `llm-provider-mistral` (`deployment.yaml:119-124`) <- `providers/mistral` | **existing** ExternalModel `mistral-large`, `provider: mistral`, endpoint `api.mistral.ai`, `credentialRef` `llm-provider-mistral-maas` (`models/values.yaml:1280-1288`, `templates/externalmodel-mistral.yaml`) + MaaSModelRef `mistral-large-maas` (`values.yaml:1211-1234`) | no: CR exists, MaaSModelRef `Ready` 2026-09-03, but no completion ever passed (payload-processing "model mismatch", ADR-0541 Status and `:460-468`) |
| 13 | `mistral-codestral` codestral-latest (`:382-388`) | saas / code, C1-C2 | Mistral native (`providers.py:189-199`) | direct | `MISTRAL_CODESTRAL_API_KEY` <- `llm-provider-mistral-codestral` (`deployment.yaml:127-132`) <- `providers/mistral-codestral` | new ExternalModel, `provider: mistral` (as #12), endpoint `api.mistral.ai`, target `codestral-latest`, `credentialRef` `llm-provider-mistral-codestral-maas` (dedicated account kept, ADR-0417) | to verify live (depends on #12's blocker) |
| 14 | `ovhcloud-gpt-oss-120b` (`:398-405`) | saas / reasoning-external, C1-C2 | OpenAI chat, OVH base URL (`providers.py:200-214`) | direct | `OVHCLOUD_API_KEY` <- `llm-provider-ovhcloud` (`deployment.yaml:135-140`) <- `providers/ovhcloud` | **existing** ExternalModel `gpt-oss-120b-ovhcloud`, `provider: openai-compatible`, `credentialRef` `llm-provider-ovhcloud-maas` (`values.yaml:1289-1297`) + MaaSModelRef `gpt-oss-120b-ovhcloud-maas` (`values.yaml:1243-1266`) | no: same as #12 |
| 15 | `ovhcloud-sdxl` stable-diffusion-xl (`image-provider-routing.yaml:34-51`) | saas-image (ADR-0415), C1-C2 | OpenAI Images API (`client.images.generate`, `image_providers.py:55-63`) | direct | `OVHCLOUD_API_KEY` (shared with #14, same Secret) | ExternalModel only if MaaS fronts `/v1/images/generations` (its proven routes are chat-shaped, `adr-0521-maas-local-traffic.md:138-139`); otherwise the named exception of ADR-0570 clause 4, keeping `llm-provider-ovhcloud` in the gateway | to verify live |

Other credentials on the gateway: the MaaS API-key fallback
`llm-provider-maas`, rendered only when `maasAdapter.apiKeyEnabled`
(`gitops/charts/ai-gateway/values.yaml:113-117`, false). Gates:
`maasAdapter.enabled: true` (`:114`) and `externalEgressEnabled: false`
(`:126`), read by `should_use_maas()` (`app/maas_adapter.py:110-126`).

CRD notes (demo333 captures). `maas.opendatahub.io/v1alpha1 ExternalModel`:
`spec.{credentialRef.name, endpoint, provider, targetModel}`, all required,
`provider` a free string. A second `ExternalModel` exists in
`inference.opendatahub.io/v1alpha1` with
`spec.externalProviderRefs[].{apiFormat, auth.{type: apikey|simple|sigv4|oauth2, secretRef.name}, path, ref.name, targetModel, weight, config}`
and `spec.modelName`; which group `MaaSModelRef.spec.modelRef.kind:
ExternalModel` resolves to is not recorded. The repo uses the `maas` group.

## 2. Quota rules

Sources: `quota-policy.yaml` (release), its generated slices
`components/ai-gateway/app/quota_budgets.yaml` and
`gitops/charts/connectivity-link/templates/quota-ratelimitpolicies.yaml`,
the engine `app/quota.py`, its call sites in `app/main.py`, and the hand-written
`tokenRateLimits` in `gitops/charts/models/values.yaml`.

Keys used today: user = `identity.sub` (`main.py:345`); group = the caller's
whole sorted group set joined with `|`, one counter per combination, not per
group (`quota.py:128-130`, generator docstring `generate_quota_enforcement.py:30-35`);
project = `X-Zuno-Project-Id` (`main.py:318,340`); class = `X-Zuno-Quota-Class`,
default `standard` (`main.py:317,339`). Counters are in-process,
epoch-aligned fixed windows (`quota.py:23-27,103-110`), checked before
dispatch (`main.py:342-348`) and charged after a successful call with
prompt+completion tokens (`main.py:755-758`, streaming `main.py:977-983`).
Denial: 429, body `{error: quota_exceeded, quota_class, dimension,
budget_tokens, window}`, header `Retry-After` = seconds to window end
(`quota.py:69-76,124`, `main.py:346-348`).

### 2a. Token budgets (the part ADR-0570 moves)

| Rule | Value (policy line) | Enforced today by | Target | Expressible? |
|---|---|---|---|---|
| standard / user | 3,000,000 per 24h (`quota-policy.yaml:93`) | `quota.py` | Kuadrant `TokenRateLimitPolicy` (TRLP) limit `standard-user`, counter `auth.identity.sub` (or attested header, D5), predicate class = standard | yes, if the MaaS AuthPolicy publishes `sub` (V8) |
| standard / group | 30,000,000 per 24h (`:94`) | `quota.py` | TRLP `standard-group`, counter `auth.identity.groups.join('|')` | yes, same caveat; `MaaSSubscription` cannot (per model, finding 5) |
| standard / project | 15,000,000 per 24h (`:95`) | `quota.py` (inert: no header, finding 1) | TRLP `standard-project`, counter `request.headers['x-zuno-project-id']`, predicate header present | only with a trusted header (D4); a Keycloak group per project is not feasible: project ids are server-minted UUIDs (ADR-0527/0528, `quota-policy.yaml:24-33`) |
| intensive / user, group, project | 500,000 / 5,000,000 / 2,500,000 per 24h (`:109-111`) | `quota.py` (inert: no task selects it) | TRLP `intensive-*`, predicate class = intensive | only with a trusted class header (D3) |
| stresstest / user, group, project | 2,000 / 8,000 / 4,000 per 5m (`:135-137`) | `quota.py`, probed by `token_quota_429.py` | TRLP `stresstest-*`, or a dedicated test group owning a small `MaaSSubscription` (D3) | yes either way |
| Cross-provider total | one counter per key across every model (`quota.py:92-115`) | `quota.py` | TRLP attached to the MaaS Gateway (not per route), counters without model | to verify: coexistence with controller-generated per-route TRLPs (V10) |

### 2b. Structural rules

| Rule | Source | Today | Target |
|---|---|---|---|
| Precedence in project context: project, then user once project exhausted, group always as ceiling | `quota-policy.yaml:35-40,139-141`; code `quota.py:144-153,161-171` | `quota.py` | **not expressible**: Limitador denies when any matching limit is exhausted; it cannot charge the user counter only after the project counter is spent. Per ADR-0570 clause 3: keep a reduced ledger, or amend ADR-0511 clause 2 to stacked ceilings (D2) |
| Precedence outside project: user then group | `:141` | `quota.py:153` | expressible as two stacked TRLP limits |
| `fail_mode` open (standard) / closed (intensive, stresstest) | `:76,103,129` | defined, never read (finding 2) | ADR-0570 clause 7 in the gateway (direct sibling only for open classes); MaaS-side outage behaviour to measure (V14) |
| Unknown class denied | `quota.py:138-143` | `quota.py` | TRLP: an unknown class matches no class predicate, so no limit applies (fail-open). Needs a catch-all limit or gateway-side class validation |
| Class selection by header, absent = standard | `quota-policy.yaml:43-45`, `main.py:317` | gateway | header forwarded to MaaS (not forwarded today: `maas_adapter.py:174` sends only `X-Zuno-Request-Id`) |
| `project_binding.validity_window` 24h | `:143-151` | Salesforce re-verification (ADR-0528), not quota | unaffected, stays with the project service |
| Denial names class, dimension, limit, window; `Retry-After` | ADR-0511 cl. 2, `quota.py:69-76` | gateway 429 | MaaS 429 content unverified (V12); gateway must map it (finding 4) |

### 2c. Request-rate rules (not moved by ADR-0570, re-targeted by WP-157)

Nine generated `RateLimitPolicy` limits per route (3 classes x user/group/project:
60/600/300, 10/60/30, 5/20/10 per 5m, `quota-policy.yaml:77-80,104-107,130-133`),
rendered by `_render_rlp` (`generate_quota_enforcement.py:138-215`) onto the
`*-quota-demo` HTTPRoutes and off by default
(`gitops/charts/connectivity-link/values.yaml:70-82`, `route.enabled: false`).
ADR-0570 Consequences: re-target or retire (D9).

### 2d. Existing MaaS limits (hand-written, ADR-0511 cl. 1 says they should not be)

Per published model (`models/values.yaml:1008-1054,1073-1117,1135-1158,1176-1199,1215-1232,1247-1264`):
`/agent_tekos` 100,000/1h priority 10; `/sales` 5,000/1h priority 1;
`system:serviceaccount:zuno-ai-run:ai-gateway` 1,000,000/1h priority 100;
Lightspeed SA 200,000/1h priority 50 on gpt-oss-20b and qwen36 only. Rendered by
`templates/maas.yaml:173-212` into `models-as-a-service`. The maas-controller
generates a TRLP from them (`templates/model-gateway.yaml:14-25`); whether it
still does with no controller running since RHOAI 3.5.0 GA is unverified (ADR-0570 Context, defect 2).

## 3. What the gateway keeps (ADR-0570 clause 6)

None of these modules changes in steps 3-5, apart from the call sites named in
section 5(c).

| Capability | Code | Tests |
|---|---|---|
| Classification routing, `local_only`, fallback order | `app/routing.py:79-137` (`candidates_for`), `main.py:356-363` | `test_two_local_providers.py`, `test_arkos_dat_classification_tiering.py` |
| ADR-0565 floor | not in `app/` yet (no match for `0565`/floor outside the optimizer) | - |
| `local_only_for`, preferences, `strict`, LoRA declarations | `app/model_routing_policy.py:160-194`, `main.py:334-336,356-369`, `main.py:575-590` | `test_model_routing_policy.py`, `test_preference_routing.py`, `test_adapter_selection.py`, `test_maas_adapter_guard.py` |
| Fallback chain | `main.py:690-837` (non-stream), `main.py:852-1010` (stream) | `test_stream_telemetry.py` |
| Semantic cache | `app/semantic_cache.py`, `main.py:636-640` | `test_semantic_cache.py`, `test_cache_integration.py` |
| Optimizer / tuning controller | `app/optimizer.py`, `main.py:63,108-158,379-381` | `test_optimizer.py` (known pre-existing failure) |
| Guardrails (ADR-0567) | `app/guardrails.py`, `main.py:388-400,440` | `test_guardrails.py` |
| Images | `app/image_routing.py`, `app/image_providers.py`, `main.py:504-551` | - |
| Routing-decision record | `app/routing_decisions.py:59-80`, `main.py:678,821,999` | `test_routing_decisions.py`, `test_routing_decision_publishing.py` |
| `zuno.model_*` metrics and spans | `app/telemetry.py:295-445` | `test_telemetry.py`, `test_local_cost_estimation.py` |
| Reasoning fold, max_tokens | `app/reasoning.py`, `main.py:193-220` | `test_reasoning_fallback.py`, `test_max_tokens_passthrough.py` |

## 4. Live verifications needed before any removal

All on demo333 first, read-only unless stated, `oc --context <ctx>` on every
command (ADR-0559). V0 is the ADR-0570 clause 8 prerequisite.

0. **MaaS front healthy and the two MaaS defects closed.** Gateway Envoy stats
   `wasm.remote_load_fetch_failures` = 0; an authenticated call through
   `maas-default-gateway` returns 200 for one local and one external model
   with a forwarded user token (closes finding 7). Today it returns 403
   `no matching subscription found for user` (2026-10-24 evidence).
1. **TRLPs exist.** `oc get tokenratelimitpolicy -A` lists the controller-generated
   policies; read their `counters`/`when` and the identity properties
   `maas-gateway-auth` publishes. `Enforced=True` is not proof (WP-54); a 429 is.
2. **ExternalModel fronts Anthropic native.** An `ExternalModel` with
   `provider: anthropic` reaches `phase: Ready`, its MaaSModelRef is `Ready`, and
   an OpenAI-format `POST .../v1/chat/completions` through MaaS returns 200
   with content and `usage.prompt_tokens > 0`, streaming included (SSE chunks
   and a final usage chunk); `payload-processing` logs show no "model mismatch".
3. **Same for Gemini native** (`provider` value to find: try `gemini`, then
   `google`); and for OpenAI (`openai`) and Codestral (`mistral`). If a native
   provider fails, the same test against the vendor's OpenAI-compatible
   endpoint with `openai-compatible` (D8).
4. **The two existing ExternalModels pass a completion** (`mistral-large-maas`,
   `gpt-oss-120b-ovhcloud-maas`): ADR-0541's blocker gone.
5. **Image generation via MaaS.** `POST /v1/images/generations` through an
   ExternalModel route for `stable-diffusion-xl-base-v10` returns 200 with
   `data[0].b64_json` that decodes; any 404/400 keeps `ovhcloud-sdxl` direct.
6. **Subscription selection among several matches.** A persona in both
   `/agent_tekos` (priority 10) and `/sales` (priority 1): the
   `selected_subscription_key` the AuthPolicy publishes and maas-api
   `/internal/v1/subscriptions/select` name the same subscription, and the 429
   arrives after that subscription's limit (100,000 vs 5,000 tokens). A user
   with no matching subscription gets 403, which the gateway must keep
   treating as "try next candidate".
7. **TRLP window semantics.** With a stresstest-sized limit: the time of the
   first 429 and of the first 200 after it, compared with an epoch-aligned
   window (`quota.py`) and a first-hit window; presence and value of
   `Retry-After`; whether a request that crosses the limit is admitted (charge
   after response) as in `quota.py`.
8. **Counter scope.** Two users of the same group on one model: separate
   counters (per user) or one shared counter (per subscription); and one user on
   two models: separate counters (per model) or shared.
9. **Streaming is metered.** A streamed call with `stream_options.include_usage`
   (sent by `stream_usage=True`, `maas_adapter.py:208`) moves the Limitador
   counter by prompt+completion tokens.
10. **Gateway-level TRLP coexists with controller TRLPs.** A test TRLP targeting
    the `maas-default-gateway` Gateway (`defaults` or `overrides`, `strategy:
    merge`) and the controller's per-route TRLPs are all `Enforced`, none
    `Overridden`, and both kinds of limit produce a 429.
11. **Project dimension.** With that TRLP keyed on
    `request.headers['x-zuno-project-id']`: the header survives the ipp ext_proc
    and Kuadrant sees it (429 after the project budget for two users sharing a
    project id; none for a request without it). Same test for
    `x-zuno-quota-class` predicates.
12. **429 contract to the UnifAI UI (WP-148).** Capture MaaS's 429 status, body
    and headers; the gateway returns its own 429 with the `quota_exceeded`
    body and `Retry-After`, never a fallback; UnifAI shows the rate-limit notice
    (`LLMRateLimitError`, WP-148 `:105-107,134-137`).
13. **Direct-Service fallback per fail_mode (ADR-0570 clause 7).** With
    `payload-processing` scaled to 0 (the drill of `adr-0521-maas-local-traffic.md:99-115`):
    a `standard` request returns 200 via the direct sibling; a `stresstest`
    request returns an error and the gateway logs show the sibling skipped; a
    MaaS 429 never reaches the sibling.
14. **MaaS behaviour when Limitador is down.** Limitador scaled to 0: does the
    MaaS gateway deny or admit? This decides whether `open` can be honoured on
    the MaaS path at all.

## 5. Proposed design for steps 3-5 (plan, not code)

### (a) SaaS ExternalModels in `gitops/charts/models`

- Replace the two hand templates `templates/externalmodel-{mistral,ovhcloud-gpt-oss-120b}.yaml`
  by one `templates/externalmodel.yaml` ranging over a list, rendering per
  entry the mirror ExternalSecret (wave -5, key `api-key`) and the
  `ExternalModel` (wave 0), unchanged in shape:

  ```yaml
  externalModels:
    - name: mistral-large            # = maas.models[].backendInferenceServiceName
      enabled: true
      provider: mistral              # free string; value per V2/V3
      endpoint: api.mistral.ai
      targetModel: mistral-large-latest
      secretName: llm-provider-mistral-maas
      vault: { path: providers/mistral, property: api_key }
    - name: gpt-oss-120b-ovhcloud     # existing values, moved
    - name: mistral-codestral         # providers/mistral-codestral
    - name: openai-gpt-4o-mini        # providers/openai
    - name: anthropic-claude          # providers/anthropic
    - name: gemini-pro                # providers/gemini
    - name: ovhcloud-sdxl             # only if V5 passes
  ```

  Each gets a `maas.models[]` entry with `modelRefKind: ExternalModel`, its
  subscriptions and `authPolicy` (as `values.yaml:1211-1266`). Vault paths stay
  one per account (ADR-0415/0416). `enabled: false` until its V2-V5 test passes.
- Subscriptions for SaaS models follow decision D5; the persona grants at
  `values.yaml:1215-1226,1247-1258` go if D5 picks the gateway identity.
- `provider-routing.yaml`: each SaaS entry gains `via_maas: true`, a per-model
  `endpoint` read from the MaaSModelRef's `status.endpoint` live (the path form
  for ExternalModel routes is not recorded) and `maas_model_ref`; `api_key_env`
  goes. Flip `maasAdapter.externalEgressEnabled` only once every enabled SaaS
  entry passed its test.

### (b) `generate_quota_enforcement.py`

- Input unchanged: the release's `policies/quotas/quota-policy.yaml`
  (`POLICY_REL`, `:62`; `--release-dir` or `release_cache`, `:384-397`).
- New output, guarded by a new value (`quotaEnforcement.tokens.enabled`, default
  false): one `TokenRateLimitPolicy` (`kuadrant.io/v1alpha1`) targeting the
  `maas-default-gateway` Gateway in `openshift-ingress`
  (`gitops/charts/openshift-ai/templates/maas-gateway.yaml:62-63`), with
  `limits.<class>-<dimension>` = `rates: [{limit: budget, window}]`,
  `counters` from `COUNTER_EXPRESSIONS` (`:77-91`, adapted per D5) and `when`
  from `_class_predicate` (`:94-135`, reused as is: same wasm-shim traps). File:
  `gitops/charts/connectivity-link/templates/quota-tokenratelimitpolicies.yaml`
  with `metadata.namespace: openshift-ingress` (Kuadrant policies live in the
  target's namespace), per WP-157 step 5; or in the openshift-ai chart beside
  the Gateway if the connectivity-link Application cannot write
  `openshift-ingress` (check its AppProject destinations).
- Optional second output if D1 keeps it: the `tokenRateLimits` of the
  `MaaSSubscription`s as a generated values file in `gitops/charts/models/`
  (for example `values-quota.generated.yaml`, added to the Applications'
  `valueFiles`), so no limit stays hand-written.
- The identity-filter lint (`_check_identity_filter`, `:288-332`) cannot read a
  controller-generated AuthPolicy from the repo: replace it, for the TRLP, by
  the V1 observation recorded here, plus a static check that the counters only
  use properties listed in a constant documented from V1.
- Keep `_render_budgets` and `BUDGETS_PATH` until the equivalence check passes;
  then remove them with `quota.py`. `--check` covers every output.
- `.github/workflows/okf-promote.yml`: add the new file(s) to `add-paths`
  (`:114-118`); remove `components/ai-gateway/app/quota_budgets.yaml` (`:118`)
  in the change that deletes `quota.py`. The generator call at `:86-88` stays.
- If D6 keeps fail modes in the gateway: a tiny generated
  `components/ai-gateway/app/quota_fail_modes.yaml` (class to `fail_mode`)
  replaces `quota_budgets.yaml` in `add-paths`.

### (c) Gateway slimming order

1. **429 is a denial, not an outage.** In both candidate loops, a MaaS 429 stops
   the loop and returns a 429 with `quota_exceeded`, class, dimension (if MaaS
   gives it) and `Retry-After`; set `max_retries=0` on the MaaS client or
   exclude 429 from retries. Tests: non-stream and stream, 429 from a via_maas
   candidate never calls the next candidate.
2. **Forward quota context** per D3/D4/D5: `X-Zuno-Quota-Class`,
   `X-Zuno-Project-Id` (and the user/group headers if D5 picks attested
   headers) in `chat_model_via_maas`'s `default_headers` (`maas_adapter.py:174`).
   Test: headers present on via_maas calls, absent on direct ones.
3. **Clause 7.** Mark direct siblings (a `direct_sibling_of: <name>` key in
   `provider-routing.yaml`, enforced by `check_docs.py`'s existing provider
   checks) and skip them unless the class's `fail_mode` is `open`, skip them on
   a 429 always. Tests: closed class never reaches a sibling; open class does on
   a 5xx/connection error only.
4. **Per SaaS provider, after its V2-V4 test:** `via_maas: true` in
   `provider-routing.yaml`; then remove its branch from `providers.py`
   (`:145-214`), keeping named exceptions; an unknown non-MaaS SaaS candidate
   raises `ProviderFactoryError`. Tests: each SaaS candidate builds the MaaS
   client; a new test asserts no `*_API_KEY` variable is read for chat
   (spy on `os.getenv`/`os.environ`).
5. **Keys out.** Remove the SaaS env entries (`deployment.yaml:101-132`), their
   `providerSecrets` keys (`values.yaml:71-77`), `platform/ai-gateway/externalsecret-{openai,gemini,anthropic,mistral,mistral-codestral}.yaml`
   and their `kustomization.yaml:28-33` lines. `ovhcloud` stays while the image
   provider is direct (D7).
6. **Quota last.** After the equivalence record: delete `app/quota.py`,
   `app/quota_budgets.yaml`, `tests/test_quota_budgets.py`, the check and the two
   consume calls (`main.py:342-348,755-758,977-983`), `_render_budgets`;
   re-target `platform/testing/token_quota_429.py` to the MaaS 429; update
   `quota-ratelimitpolicies.yaml`'s header text via the generator.
7. Suite green (the known `test_optimizer.py` failure excepted),
   `python3 platform/okf/generate_quota_enforcement.py --check`,
   `validate_quota_policy.py`, `check_docs.py`.

### (d) Decisions for the user

- **D1. Where token budgets live.** (a) `MaaSSubscription.tokenRateLimits` as
  ADR-0570 clause 2 says; (b) a generated Gateway-level TRLP as WP-157 step 5
  says; (c) both: TRLP for ADR-0511 budgets, subscriptions as entitlement plus
  a generated coarse ceiling. **Recommendation: (c).** Subscriptions are per
  model and single-select (finding 5), so they cannot carry cross-model user,
  group or project budgets; ADR-0570 clause 2's wording then needs an
  amendment by its own record.
- **D2. Precedence (project first, then user).** (a) amend ADR-0511 clause 2 to
  stacked ceilings (each applicable dimension enforced on its own); (b) keep a
  reduced ledger in the gateway for the project fallback only; (c) keep the
  whole ledger. **Recommendation: (a).** Not expressible in Limitador, and the
  project dimension is inert today (finding 1), so (b) keeps the multi-replica
  blocker for no live traffic.
- **D3. Quota classes.** (a) forward `X-Zuno-Quota-Class` and use TRLP
  predicates; (b) keep only `standard` at MaaS, prove exhaustion with a
  dedicated test group owning a tiny `MaaSSubscription`, and record `intensive`
  as unenforced until a task selects it; (c) reduced ledger for classes.
  **Recommendation: (a) only together with D5 (b); otherwise (b).** A
  client-set class header lets a direct MaaS client spread usage over several
  class counters and add their budgets.
- **D4. Project dimension.** (a) Keycloak group per project; (b) forwarded
  `X-Zuno-Project-Id` with a TRLP counter; (c) reduced ledger; (d) defer until
  ADR-0563 clause 5 is settled. **Recommendation: (d) now, then (b) under D5
  (b).** (a) needs a group per server-minted UUID, created and deleted at
  runtime.
- **D5. Identity the gateway presents to MaaS.** (a) the caller's token, as now
  (per-user MaaS accounting; each persona needs a subscription to every SaaS
  model, which conflicts with ADR-0570's C1-only rule, finding 6); (b) the
  gateway's ServiceAccount token plus gateway-attested `X-Zuno-User-Sub`,
  `X-Zuno-Groups`, class and project headers, with TRLP counters reading the
  headers only when `auth.identity` is that ServiceAccount; (c) (a) for local
  models and (b) for SaaS. **Recommendation: (b)**, if V1 shows the AuthPolicy
  publishes the username to predicates. Only the gateway holds that token, so
  headers are trustworthy, every ADR-0511 dimension becomes expressible, and
  persona groups never need a SaaS subscription. Cost: it reverses the
  2026-09-01 identity-per-caller choice (`maas_adapter.py:78-107`) for Zuno
  traffic, and MaaS's own per-user usage view only covers direct clients.
- **D6. Source of `fail_mode` after `quota_budgets.yaml` goes.** (a) a generated
  `quota_fail_modes.yaml`; (b) a chart value. **Recommendation: (a)**, so the
  policy file stays the only source (ADR-0511 clause 1).
- **D7. Image provider.** **Recommendation: keep `ovhcloud-sdxl` direct as the
  named exception** unless V5 passes; then the gateway keeps one key
  (`llm-provider-ovhcloud`).
- **D8. Providers ExternalModel cannot front natively (Anthropic, Gemini).**
  (a) keep direct with keys, as named exceptions; (b) vendor OpenAI-compatible
  endpoints with `provider: openai-compatible`; (c) drop the provider.
  **Recommendation: (b)** if it passes V3 with streaming and usage, else (a).
- **D9. Request-rate `RateLimitPolicy`.** (a) re-target onto the MaaS Gateway
  with the same keys as the TRLP; (b) re-target onto UnifAI's chat HTTPRoute;
  (c) retire. **Recommendation: (a)**, one enforcement point and one identity
  story; it needs the D5 decision first.
- **D10. ExternalModel API group.** Stay on `maas.opendatahub.io` (in use, ADR-0537)
  or move to `inference.opendatahub.io` (`apiFormat`, auth types, weights).
  **Recommendation: stay** unless V2/V3 fail there and pass on the other group.
- **D11. Credential namespace.** Keep `zuno-ai-run` (Tenant singleton,
  `templates/maas.yaml:33-69`) or a dedicated namespace. **Recommendation:
  keep**; isolation is the gateway pod no longer mounting the keys.
