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

## Decisions of 2026-10-24 (user)

Taken on the inventory in
[wp-157-inventory.md](../evidence/wp-157-inventory.md) (its D1-D11):

- **D5 - identity to MaaS.** The ai-gateway authenticates to MaaS with its
  own ServiceAccount and attaches gateway-attested user, groups, quota class
  and project, trusted only when the caller is that ServiceAccount (to
  confirm live, verification V1). This reverses the 2026-09-01 caller-token
  choice for Zuno traffic, makes every ADR-0511 dimension expressible, and
  removes the per-persona SaaS subscriptions (which today grant
  `/agent_tekos` and `/sales` on SaaS models, against ADR-0570's C1-only
  rule).
- **D1 + D2 - where budgets live.** The ADR-0511 budgets become a
  gateway-level Kuadrant `TokenRateLimitPolicy` generated from the release's
  quota policy; `MaaSSubscription`s carry entitlement plus a coarse
  generated ceiling. Precedence becomes stacked ceilings: Limitador cannot
  express the project-then-user fallback. ADR-0570 clause 2 and ADR-0511
  clause 2 carry dated amendments.
- **D3 + D4 - classes and project.** Only `standard` is enforced at MaaS for
  now; `intensive` and the project dimension stay recorded as not enforced
  until ADR-0563 clause 5 is settled, then ride the attested headers of D5.
- **D7 + D8 - providers MaaS cannot front natively.** Anthropic and Gemini go
  through their OpenAI-compatible endpoints (`provider: openai-compatible`)
  if the live test passes, otherwise they stay direct as named exceptions;
  the image provider `ovhcloud-sdxl` stays direct unless MaaS proves image
  generation.
- **D6, D9, D10, D11 - per the inventory's recommendations:** a small
  generated `quota_fail_modes.yaml` keeps the policy the only source of
  fail modes; the request-rate `RateLimitPolicy` is re-targeted onto the MaaS
  gateway after D5; ExternalModels stay in the `maas.opendatahub.io` group;
  provider credentials stay in `zuno-ai-run`.

Nothing is applied on a cluster before step 1 (the MaaS front fixed and a
forwarded-identity call proven for one local and one external model).

## Progress (2026-10-24): steps 3-5 prepared behind switches, all off

Landed on `devel` without changing a running cluster: every new behaviour
sits behind a switch that defaults to today's behaviour, and the default
renders of the touched charts are unchanged (models: the same 75 objects in
the same order, only comment lines differ; connectivity-link and ai-gateway:
byte-identical `helm template` output). The ai-gateway image picks the code
up at its next build and behaves as before until a switch is set.

| Switch (chart value) | Default | When on |
|---|---|---|
| models `externalModels[].enabled` (per provider) | `true` for `mistral-large` and `gpt-oss-120b-ovhcloud`, `false` for `mistral-codestral`, `openai-gpt-4o-mini`, `anthropic-claude`, `gemini-pro` | renders the provider's ExternalSecret (`api-key`, `zuno-ai-run`, from its existing Vault path), its `maas.opendatahub.io` ExternalModel, its plaintext DestinationRule (one per host) and its MaaSModelRef, MaaSSubscription (ai-gateway ServiceAccount only, D5) and MaaSAuthPolicy. OpenAI, Anthropic and Gemini use `provider: openai-compatible` (D8) |
| models `maas.saasSubscriptions.gatewayOnly` | `false` | the ExternalModel-backed entries keep only their `user:` subscriptions: the `/agent_tekos` and `/sales` grants on `mistral-large-maas` and `gpt-oss-120b-ovhcloud-maas` are no longer rendered (the inventory's finding 6) |
| connectivity-link `quotaEnforcement.tokenRateLimits.enabled` (+ `targetGateway.{name,namespace}`, required) | `false` | renders the generated `TokenRateLimitPolicy` `zuno-token-quota` on the MaaS Gateway (`attachment: defaults` or `overrides`, `strategy: merge`): `standard-user` 3,000,000/24h and `standard-group` 30,000,000/24h, counted on the attested headers, applied only when MaaS sees the ai-gateway ServiceAccount (D1, D2, D5) |
| connectivity-link `tokenRateLimits.enforceProjectDimension`, `enforceNonStandardClasses` | `false` | adds the generated project limits and the `intensive`/`stresstest` limits. Left off until ADR-0563 clause 5 gives a verified project id and class (D3, D4): a live limit nobody can reach would read as enforcement that is not there |
| ai-gateway `maasAdapter.gatewayIdentity.enabled` (`MAAS_GATEWAY_IDENTITY`) | `false` | MaaS calls authenticate with the pod's ServiceAccount token, never the caller's, and carry `X-Zuno-User-Sub`, `X-Zuno-Groups` (sorted, `\|`-joined, `(none)` when empty), `X-Zuno-Quota-Class`, `X-Zuno-Project-Id` (named once, `app/maas_adapter.py` `ATTESTED_HEADERS`; a test checks the generated policy reads the same names). No token or no request context refuses the call |
| ai-gateway `maasAdapter.quota429Passthrough.enabled` (`MAAS_QUOTA_429_PASSTHROUGH`) | `false` | a 429 from a via_maas candidate stops the fallback loop (no direct sibling, no SaaS) and returns the gateway's 429 `quota_exceeded` body with MaaS's `Retry-After`, streaming included; MaaS clients get `max_retries=0`. A direct SaaS 429 or a MaaS 5xx still falls back |
| ai-gateway `maasAdapter.failModes.enabled` (`QUOTA_FAIL_MODES_ENFORCED`) | `false` | reads the generated `app/quota_fail_modes.yaml`: a direct sibling of a via_maas local candidate serves only `open` classes (ADR-0570 clause 7), and a budget-config fault in `quota.py` admits `open` classes instead of denying every class (finding 2) |

The generator (`platform/okf/generate_quota_enforcement.py`) now also writes
`gitops/charts/connectivity-link/templates/quota-tokenratelimitpolicies.yaml`
and `components/ai-gateway/app/quota_fail_modes.yaml`; `--check` covers
them and `okf-promote.yml` commits them with a promotion. `quota_budgets.yaml`
and `quota.py` are unchanged.

Enable sequence, on demo333 first (`oc --context` on every command), each
step only after the verifications named (inventory section 4):

1. Step 1 done and **V0** green (MaaS front healthy, both defects closed).
2. **V1**, done 2026-10-24 (read-only): in a TokenRateLimitPolicy,
   `auth.identity` is the filter `maas-gateway-auth` publishes, which has no
   `user` key; the ServiceAccount username is `auth.identity.userid`, the
   property every controller-generated limit counts on.
   `GATEWAY_IDENTITY_PROPERTY` now reads it. Not provable before the policy
   is applied: the wasm-shim descriptor of an actual ServiceAccount call.
3. `gatewayIdentity.enabled` on the ai-gateway. Every model already grants
   the ServiceAccount; check one via_maas call per local model returns 200
   and **V8** (counter scope).
4. `maas.saasSubscriptions.gatewayOnly: true` in the models chart.
5. **V10** (pick `attachment`), **V7** and **V9**, then
   `tokenRateLimits.enabled` with the cluster's MaaS Gateway as target, on
   one connectivity-link Application only. Proof is a real 429, never
   `Enforced` (WP-54).
6. **V12** (MaaS's 429 status, body, headers) and **V6**, then
   `quota429Passthrough.enabled`; re-run the 429 half of **V13** and the
   UnifAI notice.
7. **V13** (sibling drill) and **V14** (Limitador down), then
   `failModes.enabled`.
8. Per SaaS provider, after **V4** (the two existing ExternalModels) or
   **V2/V3** (the four new ones): `externalModels[].enabled`, then (not in
   this change) `via_maas` in `provider-routing.yaml` and
   `externalEgressEnabled`. The image provider stays direct unless **V5**
   passes (D7).
9. Project and non-standard classes (`enforceProjectDimension`,
   `enforceNonStandardClasses`) only after ADR-0563 clause 5 and **V11**.

Recorded on the way:

- Gemini's OpenAI-compatible endpoint sits under `/v1beta/openai/`, and the
  `maas.opendatahub.io` ExternalModel has no path field; V3 decides whether
  the bare host works, else Gemini stays a named exception (D8 (a)) or D10
  is reopened.
- With `failModes` on, a closed-class request with a LoRA adapter declared
  loses its adapter: MaaS cannot carry adapters and the direct sibling is
  skipped, so the next eligible model serves it.
- `quota429Passthrough` defaults off rather than on: a MaaS 429 is not proven
  to mean quota only (an llm-d scheduler shedding load may answer 429), and
  a `/sales` persona's 5,000 tokens/h subscription would start failing turns
  the direct sibling serves today.

Follow-ups, deliberately not in this change (each gated on the live
equivalence checks above): delete `app/quota.py`, `app/quota_budgets.yaml`,
`tests/test_quota_budgets.py`, the ledger calls in `main.py` and
`_render_budgets` (and `quota_budgets.yaml` from `okf-promote.yml`); remove
the SaaS `providerSecrets` env and `platform/ai-gateway/externalsecret-*.yaml`
(except `ovhcloud` while the image provider is direct) and the direct SaaS
branches of `providers.py`, with a test that no SaaS key variable is read;
re-target `platform/testing/token_quota_429.py` to the MaaS 429; re-target the
request-rate `RateLimitPolicy` onto the MaaS Gateway (D9); optionally
generate the subscriptions' coarse ceilings (D1).

## Live enable on demo333 (2026-10-24)

Switches turned on one at a time through `ansible/clusters/demo333.yml`,
each verified by a second session before the next:

- **gatewayIdentity** (`maasAdapter.gatewayIdentity`): green. Persona chats
  reach MaaS under the ai-gateway ServiceAccount with the attested headers;
  `local-maas` successes went from 0 to 36 with no 401, 404 or fallback.
  It needed an ai-gateway image built from a commit carrying the code and
  the served-model-name fix in the routing ConfigMap.
- **Step A** (`quotaEnforcement.tokenRateLimits`): the TokenRateLimitPolicy
  `openshift-ingress/zuno-token-quota` is Accepted and Enforced (created
  01:42:21Z); the maas-controller's per-route policies stay Enforced; access
  control is unchanged (no token or a bogus token 401, a spoofed
  `X-Maas-Username` 403). The gateway pod was restarted at 01:49:11Z
  (same ReplicaSet, revision 1) to reload the wasm module.
  - **Group ceiling: counts.** Limitador shows a `standard-group` counter
    keyed on the real groups value for persona chats (288 tokens on qwen36),
    also after the reload. Synthetic probes with new header values did not
    always create a counter; not explained.
  - **Per-user ceiling: NOT proven.** No `standard-user` counter has ever
    appeared in Limitador, before or after the reload, although its action
    in the gateway's wasm configuration has the same shape as the group one
    and `X-Zuno-User-Sub` always carries the caller's non-empty `sub`. The
    gateway logs `proxy_on_grpc_receive invalid context_id, no match found`
    about once per call (the shim defect class seen in WP-54). The limit
    stays in the policy because it is harmless, but it is not to be
    described as enforced, and ADR-0570 clause 2 is not closed on it.
- **Step B** (`quota429Passthrough`, `failModes`): turned on with the user's
  go after step A, on the group ceiling alone. Green: persona chats answer
  200 through MaaS with no 401, 404, 500 or fallback, and the group counter
  keeps counting. Not exercised, so not claimed: a real MaaS 429 passed to
  the caller, and the fail-open path during a Limitador outage.
- **Step C** (`maas.saasSubscriptions.gatewayOnly`): turned on after step B.
  The rendered change removes only the four persona MaaSSubscriptions of
  the SaaS models and the persona groups of their auth policies. Green on
  what can be exercised: only the ai-gateway subscriptions remain, the
  entitlement policies list only its ServiceAccount, a persona token sent
  directly to the MaaS routes is refused (401), the ServiceAccount still
  passes authorization, and persona chats through qwen36 still answer.
  Not proven: a SaaS chat through MaaS. No provider in `provider-routing.yaml`
  sends mistral or gpt-oss-120b via MaaS yet (they stay direct, which this
  step does not touch), and MaaS external egress is off on demo333, so a
  SaaS route answers 500 past authorization.

Code from the V-checks (2026-10-24, user decisions, repo only, not yet in
an image):

- **Computed Retry-After (V7, V12).** MaaS's quota 429 carries no
  `Retry-After`, so with `quota429Passthrough` on the gateway computes it
  from the token windows of the policy (generated
  `app/quota_windows.yaml`), counted from the first MaaS call it saw for
  each counter key, since Limitador starts a window at its first hit. It
  takes the longest remaining window of the caller's keys (MaaS does not
  say which ceiling fired), and the class's full window when this replica
  saw no start. The WP-148 contract is unchanged.
- **Closed classes refused without MaaS (V13).** A new switch
  `maasAdapter.closedClassMaasOnly` (Ansible
  `zuno_ai_gateway_closed_class_maas_only`, default off): a `closed` class
  is served only through MaaS, so a `stresstest` request whose MaaS path
  fails is refused instead of answered by a direct SaaS fallback.

- **SaaS through MaaS (mistral-large pilot): abandoned, SaaS stays direct
  (user decision).** After the model refs were published under their path
  name (a `-maas` suffix had made every request miss its subscription, 403),
  the probe on `/zuno-ai-run/mistral-large/v1/chat/completions` hung. Cause
  (vendor): the `HTTPRoute` generated by RHOAI's ExternalModel reconciler
  has no URL rewrite on its path-prefix rule, so Mistral receives the MaaS
  path and answers 404 with a body that never completes; its header rule
  keys on `X-Gateway-Model-Name` (`mistral-large-latest`), which no
  subscription carries. The SaaS providers stay direct with their keys and
  direct branches, `externalEgressEnabled` stays off, and the MaaS-side SaaS
  objects stay in place unused. Named exception in ADR-0570.

- **Per-user ceiling: NOT enforced (order tests, user go).** Kuadrant
  orders a route's token-limit actions by limit name: the maas-controller's
  `models_as_a_service_*` subscription limits, then `standard-group`, then
  `standard-user` last. Renaming the user limit to run first made it count
  (446 tokens for three chats) and stopped the group limit, then last.
  Moving both gateway limits ahead made both count but stopped the
  per-subscription budgets (Lightspeed's 200k among them). So the wasm shim
  drops the action pairs at the end of a request. The original order is
  restored (000f6d75): **group ceiling enforced, per-subscription budgets
  enforced, per-user ceiling not enforced**. An upstream report is being
  drafted; the user limit stays in the policy, harmless, and is not to be
  described as enforced.

Open after the sequence: the per-user ceiling (upstream shim defect); the
V0-V14 equivalence checks.

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
