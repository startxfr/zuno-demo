# ADR-0570: Slim the ai-gateway by delegating quotas, keys and exposure to MaaS

- **Status:** Accepted
- **Target:** v0.11
- **Date:** 2026-10-17
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0521](0521-route-local-model-traffic-through-maas.md) (route local model traffic through MaaS)
- **Related:** [ADR-0114](0114-use-zuno-as-a-policy-router-in-front-of-openshift-ai-maas.md), [ADR-0118](0118-keep-the-ai-gateway-as-policy-router-and-defer-maas-delegation.md), [ADR-0201](0201-complete-the-openshift-ai-maas-governance-plane-integration.md), [ADR-0511](0511-define-okf-quota-policy-enforced-via-kuadrant.md), [ADR-0528](0528-rekey-project-binding-quota-and-telemetry-onto-the-zuno-project-id.md), [ADR-0537](0537-integrate-rhoai-hardware-profiles-and-maas-external-models.md), [ADR-0541](0541-integrate-mistral-and-gpt-oss-120b-as-maas-externalmodels.md), [ADR-0560](0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md), [ADR-0563](0563-forward-caller-identity-and-zuno-context-headers-from-unifai.md), [ADR-0573](0573-pilot-unifai-on-demo333-with-tekos-before-cutting-demo222-over.md)

## Context

ADR-0114 wanted Zuno to keep business decisions (classification, sovereignty,
task fit) and hand model access, subscriptions, quotas and provider
publication to OpenShift AI MaaS. ADR-0118 deferred that because MaaS was not
yet usable, and ADR-0521 then moved local-model *transport* through MaaS while
explicitly leaving quota where it was: its item 9 asks only to *evaluate*
retiring `quota.py`'s `TokenBudgetLedger`, and states that external-provider
traffic "keeps using `quota.py` regardless".

The ai-gateway therefore still owns three things MaaS was meant to own:

- **Token quotas.** `components/ai-gateway/app/quota.py` enforces ADR-0511's
  token budgets from a generated `app/quota_budgets.yaml`
  (`platform/okf/generate_quota_enforcement.py`, from
  `policies/quotas/quota-policy.yaml`), with ADR-0511 clause 2's precedence
  (project, then user, then group as ceiling) keyed on `X-Zuno-Quota-Class` and
  `X-Zuno-Project-Id` (ADR-0528). Its own docstring records that counters are
  in-process fixed windows, valid only for a single-replica gateway.
- **Provider keys.** `platform/ai-gateway/externalsecret-{openai,gemini,anthropic,mistral,mistral-codestral,ovhcloud}.yaml`
  materialise the `llm-provider-*` Secrets that `gitops/charts/ai-gateway/values.yaml`
  `providerSecrets` mounts, and every `kind: saas` entry in
  `platform/ai-gateway/provider-routing.yaml` is called directly.
- **The only governed path for SaaS models.** Two SaaS models are already
  published under MaaS as `ExternalModel`s (`gitops/charts/models/templates/externalmodel-mistral.yaml`,
  `externalmodel-ovhcloud-gpt-oss-120b.yaml`, ADR-0537), but ADR-0541 is
  `Proposed` and blocked, and `maasAdapter.externalEgressEnabled` stays off.

On the MaaS side the building blocks exist in the repository.
`gitops/charts/models/templates/maas.yaml` renders a `MaaSModelRef`, a
`MaaSSubscription` per owner and a `MaaSAuthPolicy` per published model;
`ModelsAsService.spec.externalOIDC` is enabled (`maas.externalOIDC.enabled:
true` in `gitops/charts/models/values.yaml`) so MaaS resolves the real user from
the token `app/maas_adapter.py` forwards; and each subscription carries
`tokenRateLimits` from which, per the comments in
`gitops/charts/models/templates/model-gateway.yaml`, the maas-controller
generates a `TokenRateLimitPolicy`. No `TokenRateLimitPolicy` is authored in
this repository; the request-rate side of ADR-0511 is the Kuadrant
`RateLimitPolicy` in `gitops/charts/connectivity-link/templates/quota-ratelimitpolicies.yaml`.

Three open MaaS defects stand between that design and a working path:

1. **AuthPolicy model identity.** The generated `maas-gateway-auth` derives the
   model identity from the request path in a form its `model_access` map is
   never keyed on (ADR-0201's dated notes;
   `docs/roadmap/evidence/maas-llm-path-identity-off-by-one.md`).
2. **Orphaned maas-controller webhook.** Since RHOAI 3.5.0 GA no maas-controller
   Deployment runs while its validating webhooks remain, which blocked every
   MaaS CREATE until `ansible/roles/openshift_ai/tasks/neutralize_maas_webhook_failurepolicy.yml`
   set `failurePolicy: Ignore`. With no controller, `MaaSSubscription`s are not
   reconciled, so their `TokenRateLimitPolicy` is presumably not generated -
   **unverified** on either cluster.
3. **ExternalModel payload-processing.** ADR-0541 records the
   `payload-processing` plugin rejecting every `ExternalModel` request as a
   model mismatch.

## Decision

**After the agent cutover (WP-155), every provider becomes a MaaS model and
the ai-gateway stops owning token quotas, provider keys and model exposure.
It keeps every decision that depends on Zuno context.**

1. **All providers are MaaS models.** Local `LLMInferenceService`s stay
   published as today; every SaaS provider in `provider-routing.yaml` becomes
   an `ExternalModel` with its `MaaSModelRef`, subscriptions and auth policy
   in `gitops/charts/models`. Each `provider-routing.yaml` entry becomes
   `via_maas: true`, and `maasAdapter.externalEgressEnabled` is turned on.
   Whether `ExternalModel` can front the non-OpenAI-compatible APIs (Anthropic,
   Gemini native) is **unverified**; a provider it cannot front stays direct
   and keeps its key in the gateway, named as an exception in the chart.
2. **Token quotas are enforced by MaaS.** `platform/okf/generate_quota_enforcement.py`
   stops emitting `app/quota_budgets.yaml` and instead emits the
   `tokenRateLimits` of the `MaaSSubscription`s, so ADR-0511's rule that limits
   live only in `quota-policy.yaml` finally holds for MaaS too (the
   `tokenRateLimits` in `gitops/charts/models/values.yaml` are hand-written
   today). `app/quota.py`, `quota_budgets.yaml` and the `quota.ledger.check`
   call in `app/main.py` are then removed.
3. **Removal is gated on proven equivalence, dimension by dimension.**
   `MaaSSubscription.spec.owner` names users or groups (`templates/maas.yaml`);
   it has no project and no quota-class dimension, and how MaaS chooses among
   several matching subscriptions beyond the `priority` field is
   **unverified**. Before `quota.py` goes, WP-157 records, as ADR-0521's last
   acceptance criterion already demanded, an equivalence check against
   `TokenRateLimitPolicy` for window semantics, the user and group dimensions,
   the project dimension (candidate: one Keycloak group per project), the
   quota classes and ADR-0511's precedence. A dimension MaaS cannot express is
   either kept in a reduced ledger in the gateway, or ADR-0511 clause 2 is
   amended by its own record; it is never dropped silently.
4. **Keys leave the gateway.** The `llm-provider-*` ExternalSecrets and the
   `providerSecrets` mounts are removed; provider keys exist only as
   `ExternalModel.spec.credentialRef` Secrets in the models namespace. The
   gateway authenticates to MaaS with the caller's token (already the default
   in `_maas_bearer_token`). The image provider (`ovhcloud`, ADR-0415) keeps
   its key unless MaaS can front image generation - **unverified**.
5. **Exposure belongs to MaaS.** Model consumers other than Zuno agents -
   programmatic clients, Lightspeed, developers - reach models through MaaS
   subscriptions, never through the ai-gateway, which stays reachable only
   in-cluster from the callers its NetworkPolicy admits.
6. **What the gateway keeps.** Classification routing and the ADR-0565 floor,
   `local_only` and `local_only_for`, the fallback chain, per-(agent, task)
   preferences and `strict`, LoRA adapter selection, the semantic cache, the
   optimizer, guardrails (ADR-0567), images, the routing-decision record and
   the `zuno.model_*` metrics and spans.
7. **Direct-Service fallback follows the quota fail mode.** ADR-0521 item 6
   keeps a direct-Service sibling behind each `via_maas` local candidate.
   Once MaaS is the only quota point, that sibling bypasses quota; the gateway
   therefore uses it only for quota classes whose `fail_mode` in
   `quota-policy.yaml` is `open` (today `standard`), and skips it for `closed`
   classes. SaaS candidates get no direct sibling.
8. **Prerequisite.** None of clauses 1-5 is executed on a cluster before the
   three defects in Context are fixed there and an authenticated call through
   `maas-default-gateway` for one local and one external model is
   live-proven with a forwarded user token.

## Planned supersession

At the gateway slimming (WP-157), after the agent cutover:

- **ADR-0511, in part** - clause 3(b) (AI Gateway budget configuration
  generated from the policy) and clause 4's "token-budget dimension is
  enforced in AI Gateway regardless of placement". Clauses 1, 2 and 5 stand,
  subject to clause 3 above.
- **ADR-0528, in part** - clause 4's keying of the *token* quota on
  `X-Zuno-Project-Id` at the gateway, only for the dimensions WP-157 proves
  MaaS can carry. Its telemetry keying (`zuno.project_id` span attribute)
  stands.
- **ADR-0118, in part** - "the AI Gateway remains Zuno's policy router with
  its own provider abstraction": the policy router stays (ADR-0560), its own
  provider abstraction does not.
- **ADR-0521, in part** - item 9's statement that external-provider traffic
  keeps using `quota.py` regardless.

## Consequences

The gateway loses its only multi-replica blocker named in `quota.py`'s own
docstring, and with it the duplicate quota engine ADR-0114 objected to.
Provider credentials concentrate in one namespace under MaaS governance.
MaaS becomes a hard dependency of every model call, local and SaaS; clause 7
keeps local `standard`-class chat available through a MaaS outage, but SaaS
models have no such escape.

Users see MaaS's quota error instead of the gateway's: ADR-0511 requires the
denial to name class, dimension, limit and window, and whether MaaS's 429
carries enough to render that (ADR-0569's quota UX) is **unverified**.

The Kuadrant request-rate `RateLimitPolicy` targets the current agent chat
HTTPRoute (`quota-ratelimitpolicies.yaml`); after ADR-0561 the chat path is
UnifAI's, and WP-157 re-targets or retires it.

## Security considerations

Classification stays the stricter outer policy, unchanged from ADR-0114 and
ADR-0118: the gateway filters candidates before choosing a transport, and a
MaaS subscription never makes a SaaS model eligible for C2/C3 content it is
not eligible for in `provider-routing.yaml`. Clause 5 creates a path that does
not cross Zuno's classification at all: a programmatic MaaS client of a SaaS
`ExternalModel` is governed only by its subscription. MaaS subscriptions to
SaaS models are therefore granted only to groups whose use is limited to C1
content, recorded beside each subscription.

Quota denial must remain fail-closed per class (ADR-0511); clause 7 is the one
deliberate exception and mirrors the policy file's own `fail_mode`.

## Operational considerations

Each new SaaS model costs a `MaaSModelRef`/`MaaSSubscription`/`MaaSAuthPolicy`
triple and an `ExternalModel`, like every local model since ADR-0521. Key
rotation becomes a Vault re-seed of the `ExternalModel` credential only. The
WP-157 equivalence check and the live proofs run first on demo333 (powered off
at the time of writing; the user must be asked to power it on), then on
demo222 outside demo freezes, with `--context` passed explicitly to every `oc`
command (ADR-0559). Verifying the generated `TokenRateLimitPolicy` objects
exist (`oc --context <ctx> get tokenratelimitpolicy -A`) is the first check,
since defect 2 may mean they do not.

## Amendment (2026-10-24, user decision on the WP-157 inventory)

**Clause 2** is amended: MaaS `MaaSSubscription` limits are per model and
MaaS selects one subscription per request, so they cannot carry ADR-0511's
cross-model budgets. Those budgets become a gateway-level Kuadrant
`TokenRateLimitPolicy` generated from the release's quota policy by
`platform/okf/generate_quota_enforcement.py`; subscriptions carry entitlement
and a coarse generated ceiling. The ai-gateway presents its own
ServiceAccount to MaaS with gateway-attested user, groups, quota class and
project (WP-157 decision D5), which also ends the per-persona SaaS
subscriptions. Details and the live verifications that gate each removal:
[WP-157](../roadmap/work-packages/wp-157-slim-the-ai-gateway-via-maas.md),
[inventory](../roadmap/evidence/wp-157-inventory.md).

## Amendment (2026-10-24, SaaS providers stay direct: named exception)

**Clauses 1 and 4** take a named exception, by user decision after the
mistral-large pilot. The chat SaaS providers (`mistral`,
`mistral-codestral`, `ovhcloud-gpt-oss-120b`, `openai`, `gemini`,
`anthropic`) stay **direct** from the ai-gateway, which keeps their keys
and its direct branches; `maasAdapter.externalEgressEnabled` stays off.
The reason is a vendor defect: the `HTTPRoute` that RHOAI's ExternalModel
reconciler generates has no URL rewrite on its path-prefix rule, so the
provider receives `/zuno-ai-run/<model>/v1/chat/completions` and answers
404 (seen as a hang), while its header rule matches on
`X-Gateway-Model-Name`, an identity no subscription carries. A generated
route is not edited by hand. The exception is bounded as before: SaaS is
eligible for C1 (and C2 where `provider-routing.yaml` says so) only, the
gateway's classification stays the outer policy, and the MaaS-side SaaS
objects (`ExternalModel`, `MaaSModelRef`, the subscription restricted to
the ai-gateway ServiceAccount, auth policy) stay in place, unused, ready
for a fixed reconciler. Local models are served through MaaS and their
token budgets are enforced by the gateway-level `TokenRateLimitPolicy`
(clause 2 as amended): the **group ceiling is enforced**, the controller's
**per-subscription budgets are enforced**, and the **per-user ceiling is
NOT enforced**. The Kuadrant wasm shim on demo333 drops the token-limit
action pairs at the end of a request (live order tests, 2026-10-24), and
Kuadrant orders those pairs by limit name, so the user limit, last, is
never counted; moving it ahead stopped other limits from counting instead.
An upstream report is being drafted; the per-user ceiling stays a
follow-up of
[WP-157](../roadmap/work-packages/wp-157-slim-the-ai-gateway-via-maas.md).

