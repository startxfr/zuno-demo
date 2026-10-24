# WP-157: Slim the ai-gateway by delegating quotas, keys and exposure to MaaS

- **State:** Not started
- **ADRs:** [ADR-0570](../../adr/0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md)
- **Depends on:** [WP-155](wp-155-migrate-remaining-agents-and-cut-demo222-over.md)
- **Related:** [ADR-0118](../../adr/0118-keep-the-ai-gateway-as-policy-router-and-defer-maas-delegation.md), [ADR-0511](../../adr/0511-define-okf-quota-policy-enforced-via-kuadrant.md), [ADR-0528](../../adr/0528-rekey-project-binding-quota-and-telemetry-onto-the-zuno-project-id.md), [ADR-0560](../../adr/0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md), [WP-54](wp-54-quota-policy-and-kuadrant-translation.md), [WP-156](wp-156-retire-zuno-agent-and-rag-code.md)
- **Target:** v0.11
- **Estimated files touched:** ~20 in `zuno-demo` — MaaS model resources for SaaS providers, Kuadrant TokenRateLimitPolicy generation, `components/ai-gateway/app/{quota.py,quota_budgets.yaml,main.py,maas_adapter.py,providers.py}`, their tests, `platform/okf/generate_quota_enforcement.py`, `platform/ai-gateway/externalsecret-*.yaml`, `gitops/charts/{ai-gateway,connectivity-link,models}`.

> After cutover the gateway keeps what only it does — classification
> routing, fallback, preferences and LoRA, cache, optimizer, images, routing
> metrics — and hands quotas, SaaS credentials and model exposure to the
> platform. It does not start while the MaaS path itself is broken.

## Goal

Every model, local or SaaS, is reached through RHOAI MaaS; token quotas are
enforced by Kuadrant `TokenRateLimitPolicy`; the ai-gateway holds no SaaS
API key and no quota state; `app/quota.py` and the in-gateway budget
generation are gone; routing behaviour and metrics are unchanged.

## Steps

1. **Prerequisite — fix the open MaaS defects (blocking).** Two are open:
   the AuthPolicy `model_identity` path-vs-map-key mismatch that denies all
   callers, and the RHOAI 3.5.0 maas-controller orphan webhook (mitigated
   with `failurePolicy=Ignore`, not fixed). Read
   `docs/roadmap/evidence/maas-llm-path-identity-off-by-one.md` and
   `docs/roadmap/evidence/adr-0521-maas-local-traffic.md`. Fix or confirm a
   vendor fix for both, with a passing live request through MaaS for a
   local model. Do not start step 2 until this holds.

   Observed on demo333 on 2026-10-22 (third item, to look at in the same
   step): the MaaS front (`maas-default-gateway`) answers HTTP 503 to most
   `qwen36-27b-instruct` calls under load (about 140 of 170 in one hour, while
   the UnifAI evaluations ran), whereas the model's own `kserve-workload-svc`
   answers 200 right after. The gateway pod was stable (running since 10:36),
   the model pod and its router-scheduler were Running with no restart. The
   ai-gateway recovers by trying its direct provider next, at the cost of one
   retry and, when several providers fail in turn, tens of seconds. Suspect the
   llm-d scheduler refusing requests on a single replica; confirm with the
   scheduler's logs and metrics before changing quotas or replicas.

2. **Inventory.** Read `components/ai-gateway/app/quota.py`,
   `app/quota_budgets.yaml`, `tests/test_quota_budgets.py`,
   `platform/okf/generate_quota_enforcement.py`,
   `gitops/charts/connectivity-link/templates/quota-ratelimitpolicies.yaml`,
   `app/maas_adapter.py`, `app/providers.py`, the `providerSecrets` block of
   `gitops/charts/ai-gateway/values.yaml` and
   `platform/ai-gateway/externalsecret-*.yaml`. List each quota rule and
   each provider with its target MaaS construct.
   Progress (2026-10-24): inventory, live verifications and a plan for steps
   3-5 with open decisions in
   [`wp-157-inventory.md`](../evidence/wp-157-inventory.md).

3. **SaaS providers as MaaS models.** For each SaaS provider (OpenAI,
   Gemini, Anthropic, Mistral, Codestral, and the image provider), declare
   an external model in MaaS with its credentials from Vault via
   ExternalSecret in the MaaS namespace. Run `oc explain` on the MaaS CRDs
   before authoring them (the CRD names are not recorded in the repo; do
   not guess). Local KServe models are already reachable through MaaS
   (ADR-0521 evidence).

4. **Gateway routes everything through MaaS.** Make `app/maas_adapter.py`
   the only outbound path; remove direct SaaS clients from
   `app/providers.py`; keep C1/C2/C3 routing (`app/routing.py`,
   `platform/ai-gateway/provider-routing.yaml`), fallback, preferences/LoRA
   (`app/model_routing_policy.py`), semantic cache, optimizer, images and
   `zuno.model_*` metrics untouched. Remove the `providerSecrets` env from
   `gitops/charts/ai-gateway/templates/deployment.yaml` and the
   `platform/ai-gateway/externalsecret-*.yaml` files for SaaS keys.

5. **Quotas to Kuadrant.** Change `platform/okf/generate_quota_enforcement.py`
   to emit `TokenRateLimitPolicy` objects (keyed on the zuno project id per
   ADR-0528) into `gitops/charts/connectivity-link/`, next to the existing
   request-rate `RateLimitPolicy`. Delete `app/quota.py`,
   `app/quota_budgets.yaml` and `tests/test_quota_budgets.py`; keep the 429
   contract the UnifAI UI handles (WP-148).

6. **Tests.** ai-gateway suite green (the known pre-existing
   `test_optimizer.py` failure excepted); add a test that no SaaS key env var
   is read; `python3 platform/okf/validate_quota_policy.py` and
   `python3 platform/docs/check_docs.py` green.

7. **Live on demo333 first.** demo333 is powered off; ask the user to power
   it on. With `oc --context <demo333-context>`: one request per provider
   class through UnifAI -> ai-gateway -> MaaS; exhaust a test token quota
   and see the 429 in the UnifAI UI; `zuno_provider` per classification
   unchanged versus before. demo222 follows only outside a demo freeze,
   with parallel sessions informed.

## Acceptance

Both MaaS defects closed with live evidence; the ai-gateway image contains
no `quota.py` and its Deployment no SaaS key; token quotas are visible as
`TokenRateLimitPolicy` objects Enforced on demo333 and a quota breach
returns 429; routing decisions for the tekos scenarios match the
pre-change run.

## Open questions

- Can MaaS front SaaS providers with per-provider credentials at all in
  RHOAI 3.5, and with streaming? Unverified; step 3 starts with `oc explain`.
- `Accepted` and `Enforced` on a Kuadrant policy never proved the wasm
  filter loaded (WP-54 lesson); how is enforcement proved — only by a real
  429?
- Does the semantic cache key need the MaaS model id instead of the
  provider name once every call goes through MaaS?
