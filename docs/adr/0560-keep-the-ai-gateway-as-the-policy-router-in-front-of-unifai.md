# ADR-0560: Keep the ai-gateway as the policy router in front of UnifAI

- **Status:** Accepted
- **Target:** v0.11
- **Date:** 2026-10-17
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0009](0009-separate-agent-runtime-from-ai-inference-gateway.md) (separate the agent runtime from the AI inference gateway)
- **Related:** [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md), [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md), [ADR-0118](0118-keep-the-ai-gateway-as-policy-router-and-defer-maas-delegation.md), [ADR-0521](0521-route-local-model-traffic-through-maas.md), [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md), [ADR-0563](0563-forward-caller-identity-and-zuno-context-headers-from-unifai.md), [ADR-0565](0565-derive-data-classification-from-okf-and-only-allow-raising-it.md), [ADR-0567](0567-move-trustyai-guardrails-into-the-ai-gateway.md), [ADR-0570](0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md)

## Context

ADR-0561 adopts UnifAI (fork `startx-unifai`, branch `devel`) as the agent
platform in place of `components/agent-runtime`, `agent-bff` and
`agent-frontend`. That raises a question the replacement does not answer by
itself: does UnifAI also replace `components/ai-gateway`?

It cannot, because UnifAI is not a model gateway. Each agent node calls its
provider directly through an LLM "element": in the fork,
`multi-agent/lib/mas/elements/llms/openai_compatible/openai_compatible.py`
builds a plain `openai.OpenAI(api_key=..., base_url=..., **extra)` client per
LLM resource, and the sibling elements (`openai`, `google_genai`, `mock`) do
the same against their vendors. Provider credentials live in the LLM resource
itself (`BaseLLMConfig.api_key` in `elements/llms/common/base_config.py`,
stored encrypted in MongoDB). There is no routing between providers, no
fallback chain, no quota, no cache, no guardrail and no metric beyond optional
Langfuse tracing. An agent that points at a SaaS provider simply calls it.

`components/ai-gateway` is the opposite: an OpenAI-compatible
`POST /v1/chat/completions` (`app/main.py`) whose whole purpose is policy. It
resolves an ordered candidate list from the caller's
`X-Zuno-Data-Classification` and `X-Zuno-Local-Only` headers
(`app/routing.py` `RoutingTable.candidates_for`, configured by
`platform/ai-gateway/provider-routing.yaml`); applies per-(agent, task)
preferences, `strict` exclusions, `local_only_for` restrictions and LoRA
adapter selection from `app/model_routing_policy.py`; walks the candidates
with `_invoke_with_fallback`; reaches local models through MaaS when
`via_maas` is set (`app/maas_adapter.py`, ADR-0521); meters tokens
(`app/quota.py`); caches semantically within a classification and task
boundary (`app/semantic_cache.py`, cache key includes classification,
local-only and task); emits `zuno.model_*` OTel metrics and a `model_call`
span carrying `zuno.classification`, `zuno.agent`, `zuno.run_id` and
`zuno.project_id` (`app/telemetry.py`); publishes the per-request routing
decision at `GET /v1/routing-decisions/{request_id}`; and serves images
(`/v1/images/generations`).

The C1/C2/C3 rule (ADR-0021) and the Confluence-stays-local rule (ADR-0035)
are enforced in that one place. Letting UnifAI agents call providers directly
would scatter those rules across every LLM resource a UnifAI user can create,
and nothing in UnifAI would enforce them.

## Decision

**The ai-gateway remains Zuno's model policy router, and every UnifAI LLM
resource used by a Zuno agent is an `openai_compatible` resource whose
`base_url` points at it.** The replacement scope of ADR-0561 is the agent
layer - orchestration, state, UI, RAG, tool wiring - and stops at the
gateway's front door.

1. **One LLM resource per routing intent, not per provider.** The resources
   the unifai-operator emits for Zuno agents (ADR-0564) name a logical model
   (the `model` field the gateway already receives as `requested_model`), point
   at the in-cluster gateway Service, and carry no provider key. The concrete
   provider is chosen by the gateway, never by the resource.
2. **No direct provider resource for Zuno agents.** No UnifAI LLM resource
   that a Zuno agent uses may point at a SaaS vendor endpoint or at a KServe
   workload Service directly. A resource that bypasses the gateway bypasses
   ADR-0021, ADR-0035 and ADR-0550's `local_only_for` restriction at once.
3. **The gateway's request contract is the integration contract.** The
   caller identity and the `X-Zuno-*` context headers it consumes today -
   `Authorization`, `X-Zuno-Data-Classification`, `X-Zuno-Local-Only`,
   `X-Zuno-Agent`, `X-Zuno-Task`, `X-Zuno-Request-Id`, `X-Zuno-Run-Id`,
   `X-Zuno-Project-Id`, `X-Zuno-Quota-Class`, `X-Zuno-Max-Tokens` - are what
   UnifAI must send. How UnifAI produces them is ADR-0563; how classification
   is derived is ADR-0565. The gateway does not grow a UnifAI-specific
   endpoint.
4. **What the gateway owns is reconsidered separately.** Guardrails move in
   (ADR-0567); quotas, provider keys and exposure move out to MaaS after the
   agent cutover (ADR-0570). Classification routing, fallback, preferences,
   LoRA adapters, cache, optimizer, images and routing metrics stay.

ADR-0009's separation is not reversed but restated with a new left-hand side:
orchestration, state and tooling belong to UnifAI's multi-agent service (MAS);
inference routing, model policy and provider fallback belong to the
ai-gateway.

## Planned supersession

None. ADR-0009 stays in force with UnifAI MAS in the role it names "Agent
Runtime"; at cutover (WP-156) it receives a dated correction note recording
that substitution, which retires no clause. ADR-0118's "keep the gateway as
policy router" stands unchanged.

## Consequences

The classification guarantee keeps a single enforcement point, already covered
by `evaluations/tekos/security_checks.py`'s
`ai_gateway_local_only_forces_local_provider`, and it does not have to be
re-proven inside UnifAI. Routing, fallback and LoRA behaviour carry over to the
new agents unchanged, and the `zuno-*` dashboards keyed on `zuno.model_*`
metrics keep working through the cutover.

UnifAI loses the per-resource provider choice its UI offers for Zuno agents:
what the UI shows as "the model" is a logical name the gateway resolves. The
actual provider must be surfaced another way (`zuno_provider` and
`/v1/routing-decisions/{id}`, ADR-0569).

The gateway's NetworkPolicy (`gitops/charts/ai-gateway/templates/networkpolicy.yaml`)
admits `agent-runtime`, `acceptance-gate` and `mcp-gateway` pods today; it must
admit the UnifAI MAS pods (and, if Temporal is used, its workers) and, after
WP-156, stop admitting `agent-runtime`.

## Security considerations

The gateway authenticates every call (`app/auth.py` `validate_token`, Keycloak
JWKS) but trusts the context headers it is given; today that trust rests on
the NetworkPolicy above admitting only platform code. Under UnifAI, the code
that composes those headers runs inside MAS, where users can also create their
own LLM resources (`CardContext.CUSTOM` in `BaseLLMConfig`). The ingress
boundary therefore widens from "agent-runtime" to "anything MAS executes".
Clause 2 is the mitigation for direct provider calls; ADR-0563 and ADR-0565
carry the mitigation for header forgery. Whether UnifAI can restrict creation
of custom LLM resources to administrators is **unverified** and must be
answered in WP-146.

Provider credentials stay out of UnifAI's MongoDB entirely for Zuno agents:
the only secret an LLM resource needs is the caller's own token, which is
forwarded, not stored (ADR-0563).

## Operational considerations

A gateway outage now stops every UnifAI agent, as it stops every Zuno agent
today; the PDB and single-replica posture are unchanged (ADR-0101).
Verification at pilot (WP-151, demo333 - powered off at the time of writing,
the user must be asked to power it on): a UnifAI agent call produces a
`model_call` span with `zuno.agent` set, `GET /v1/routing-decisions/{id}`
answers for its request id, and an LLM resource pointed at a SaaS endpoint is
absent from the operator-emitted set. Any `oc` command passes `--context`
explicitly (ADR-0559).
