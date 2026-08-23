# ADR-0201: Complete the OpenShift AI MaaS governance plane integration

- **Status:** Partially implemented (local model published and consumable through MaaS, governance pairing proven live; the actual authenticated end-to-end request is still blocked - a NetworkPolicy allow-list gap was confirmed and fixed 2026-08-23 without resolving the request, so a second, still-unidentified blocking layer exists; see 2026-08-23 note)

## Implementation note (2026-08-23) — NetworkPolicy fix landed and verified, but did not resolve the 500; a second blocking layer exists

Landed WP-27's proposed fix for the 2026-08-21 note's NetworkPolicy finding,
additively rather than patching the RHOAI-owned policy (which the
2026-08-21 note already proved doesn't stick): `payload-pre-processing`'s
NetworkPolicy is actually **our own** resource (ArgoCD-tracked, no
`ModelsAsService` ownerReference - RHOAI's controller only auto-generates
one for `payload-processing`), so it was extended directly to also allow
`gateway-name: maas-default-gateway`; a brand-new, separately-owned
NetworkPolicy (`payload-processing-maas-gateway-allow`) was added for
`payload-processing` rather than editing the operator-owned one - unions
with it instead of fighting its controller. Both confirmed live via
`oc get networkpolicy -o yaml` after an ArgoCD hard-refresh/sync: exactly
the rules intended.

**The authenticated request still 500s, identical signature**: `envoy
ext_proc` on `maas-default-gateway` still reports `Received gRPC error on
stream: 14 ... TLS_error:...Connection_reset_by_peer`, and
`payload-processing`/`payload-pre-processing`'s istio-proxy sidecars still
log **zero** lines for the request window (checked a 10-minute window, not
just the immediate one) - meaning the NetworkPolicy layer was never
actually the (sole) blocker, contrary to the 2026-08-21 note's conclusion.
Ruled out as alternates: no `AuthorizationPolicy` or `PeerAuthentication`
exists anywhere in the cluster (`oc get peerauthentication -A` empty), so
this isn't a mesh-wide STRICT-mTLS mismatch.

**New lead, not yet chased**: a live `EnvoyFilter` named `payload-processing`
in `openshift-ingress` (owned by RHOAI's `Config.maas.opendatahub.io/default`
CR) inserts the `ipp-pre`/`ipp` ext_proc filters (the ones that call out to
`payload-pre-processing`/`payload-processing` on port 9004) relative to a
Kuadrant wasm-plugin subfilter,
`extensions.istio.io/wasmplugin/openshift-ingress.kuadrant-maas-default-gateway`.
This cluster has a separately-tracked, already-open Kuadrant wasm-shim
defect (roadmap WP-54, 2026-08-21: "real Authorino bypass proves wasm-shim
itself is broken, not our config"). If that wasm plugin isn't correctly
present/positioned in the live filter chain, this `EnvoyFilter`'s
`INSERT_BEFORE`/`INSERT_AFTER` anchor could silently fail to attach the
ext_proc filters as configured - a plausible next root cause, not yet
verified. Next step for a future pass: inspect the live Envoy config dump
on `maas-default-gateway`'s pod (`istioctl proxy-config listener` /
`config_dump`) to confirm whether the wasm-plugin subfilter and both
ext_proc filters are actually present and correctly ordered in the running
filter chain.

## Implementation note (2026-08-21) — the real blocker is a NetworkPolicy allow-list, and it isn't patchable

Picked this back up with the narrow sidecar-inject remediation (option a
from the 2026-08-18 note) already live from an earlier pass:
`payload-processing`/`payload-pre-processing` both carry a real
`istio-proxy` native sidecar (confirmed via `sidecar.istio.io/status`,
pods `2/2 Ready`) - injection itself was never the remaining problem.

The authenticated request still 500s identically. Root-caused further:
Envoy's `ext_proc` filter on `maas-default-gateway` reports `Received
gRPC error on stream: 14 ... TLS_error:...Connection_reset_by_peer` on
every attempt, but `payload-processing`'s own `istio-proxy` logs **zero**
lines for the same window - the connection never reaches the destination
sidecar at all. The actual cause: both RHOAI-owned NetworkPolicies in
`openshift-ingress` (`payload-processing`, `payload-pre-processing`,
owned by the `ModelsAsService` controller) allow port-9004 ingress only
from pods matching `gateway.networking.k8s.io/gateway-name:
data-science-gateway` - `maas-default-gateway` was never in the
allow-list, so the connection is dropped before any TLS handshake is
even attempted. The earlier note's "TLS error" framing was Envoy's own
generic label for an upstream reset, not proof the failure was
TLS-specific.

No CRD field on `ModelsAsService.spec` (`oc explain
modelsasservice.spec --recursive`) exposes this allow-list. A live
`kubectl patch --type=json` adding a `maas-default-gateway` podSelector
entry to both NetworkPolicies' `ingress[0].from` was attempted and
**did not stick even momentarily** - re-reading the object immediately
after a successful-looking `patched` response shows the original,
unmodified list, with no error surfaced and no Event recorded. Something
(most plausibly the `ModelsAsService` controller's own reconcile loop,
possibly assisted by a webhook) enforces this spec synchronously on
every write; there's no drift window to exploit even briefly. This isn't
a "try again with more force" situation - it's a genuine, closed platform
constraint in this RHOAI 3.5-EA2 build, the same class of finding as the
`EnvoyFilter` `failure_mode_allow` gap the 2026-08-18 note already
documented, just one layer earlier in the request path.

Remaining options, per the 2026-08-18 note's own framing, are unchanged
in kind: (a) file this as an upstream RHOAI defect and wait, since (b)
"force it live" has now been tried at the NetworkPolicy layer too and
doesn't hold, or (c) get out-of-band access to patch the
`ModelsAsService` operator/controller itself (its Subscription/CSV,
outside this repo's normal change surface) - not attempted this pass, a
materially bigger, more consequential action than anything tried so far.

## Implementation note (2026-08-18, part 2)

Attempted the actual authenticated end-to-end request (acceptance bullets
2-3: differentiated access, `MaaSAuthPolicy` denial) with real personas
from the Keycloak realm (`tekos-entitlement-only-user-01`,
`sales-role-only-user-01`, `finance-role-only-user-01` as the negative
case - the chart's own `authPolicy` comment already named `finance` as
the intended negative test). Found and fixed two real bugs in our own
chart along the way, then hit a genuine platform limitation that stopped
short of a full proof:

1. **Fixed**: `gitops/charts/openshift-ai/templates/maas-gateway.yaml`'s
   `maas-gateway-route` pointed `spec.to.name` at `maas-default-gateway`,
   but Istio's Gateway API controller actually names the auto-deployed
   Service `maas-default-gateway-istio` - the chart's own comment had
   flagged this as unverified. Every external request through this Route
   had 503'd since it was first applied; nothing had exercised it with a
   real HTTP client before now.
2. **Fixed**: the auto-provisioned gateway pod OOMKilled repeatedly (30
   restarts in 13h) at Istio's stock gateway-proxy sizing (500m/256Mi) -
   sized up via the same `infrastructure.parametersRef` ConfigMap
   mechanism already used for the Service override.
3. **Blocked** (platform-level, not our chart): with both fixes live, a
   real OpenShift-token-authenticated request (confirmed via
   `TokenReview` - `groups: ["agent_tekos", ...]` present and valid)
   reaches the gateway but returns `500` before ever reaching the
   `AuthPolicy`'s group-membership check. Root cause: an `EnvoyFilter`
   (`payload-processing`, owned by RHOAI's own
   `Config.maas.opendatahub.io/default` - empty spec by design, "reserved
   for future configuration", no supported toggle) wires the gateway's
   `ext_proc` filter to `payload-processing`/`payload-pre-processing`
   pods in `openshift-ingress` via what Istio treats as a mesh-internal
   (`outbound|9004|...`) cluster - but those pods are not mesh-injected
   (`1/1`, confirmed no sidecar, namespace carries no `istio-injection`
   label). The resulting TLS handshake resets
   (`Connection_reset_by_peer`), and since the main `ipp` filter has
   `failure_mode_allow: false` (unlike `ipp-pre`, which already fails
   open), the whole request 500s. A quick pod-level
   `sidecar.istio.io/inject: "true"` annotation on both Deployments did
   not trigger injection (reverted, no lasting effect) - the namespace
   itself isn't configured for opt-in pod-level injection. Broadening
   mesh injection to all of `openshift-ingress` (which also hosts the
   core OpenShift Router) was judged too broad-blast-radius to attempt
   without explicit approval, and a live patch to force
   `failure_mode_allow: true` on the RHOAI-owned EnvoyFilter was blocked
   by the session's own safety guardrail as a security-adjacent ingress
   change.

This appears to be a genuine defect/gap in this RHOAI 3.5 EA2 build's own
MaaS payload-processing pipeline (an early-access component), not
something resolvable from this repo's gitops tree alone. Options for a
future pass: (a) get explicit approval to sidecar-inject
`payload-processing`/`payload-pre-processing` specifically (narrower than
namespace-wide), (b) get explicit approval to force
`failure_mode_allow: true` on the RHOAI-owned EnvoyFilter live (non-durable
- would need reapplying if the `Config` controller ever reconciles it),
or (c) file this as an upstream RHOAI EA defect and wait for a fix.

## Implementation note (2026-08-18, part 1)

The `LLMInferenceService` path from the 2026-08-16 note is now live and
verified end-to-end on demo222:

- A 3rd GPU node was added and the model published as a
  `serving.kserve.io/v1alpha2 LLMInferenceService`
  (`qwen25-7b-instruct-maas-backend`) - `Ready=True` across all 8
  sub-conditions, backing pod `2/2 Running`.
- Its `hf://` download hung indefinitely on every attempt (verified not a
  network issue); switched to `s3://`, hosting the model in the same
  bucket/credential `rag-ingestion` already uses - see
  `gitops/charts/models/templates/maas.yaml`'s ExternalSecret comment for
  the full diagnosis.
- Found and fixed a real architecture gap in the governance wiring: this
  RHOAI 3.5 EA2 MaaS build centralizes `MaaSSubscription`/`MaaSAuthPolicy`
  into an operator-generated `models-as-a-service` namespace
  (`MAAS_SUBSCRIPTION_NAMESPACE` on the `maas-controller` Deployment) -
  its tenant controller never reconciles anything created elsewhere, so
  the two Keycloak-group subscriptions and the auth policy had to move
  there (`MaaSModelRef` itself stays in `zuno-ai-run` alongside the
  model - only Subscription/AuthPolicy are centralized).
- Live result: `MaaSModelRef.status.phase: Ready`
  ("Governed and runtime-healthy"), both `MaaSSubscription`s and the
  `MaaSAuthPolicy` `Active`.

Acceptance criteria bullet 1 (local model published and consumable
through MaaS) is now met. Still open: an authenticated end-to-end request
through the MaaS gateway with a real persona token (an in-cluster
unauthenticated sanity call hit Istio's automatic mTLS interception, not
a service defect - the platform's own health probes and the
`MaaSModelRef`'s `RuntimeHealthy` condition already confirm the backend
answers correctly), the `MaaSAuthPolicy` positive/negative denial proof,
API-key lifecycle, and usage-metric correlation (bullets 2-6 of the
Required v0.1 implementation list).

## Implementation note (2026-08-16)

Attempted the live rollout on demo222; the chart's own flagged `# CONFIRM`
on `modelRef.kind: ExternalModel` is now resolved by direct schema
inspection (`oc explain`), and the answer blocks activation as designed
rather than confirming it:

- `ExternalModel.spec.externalProviderRefs[].ref` points at an
  `ExternalProvider`, whose `spec.endpoint` is documented as *"FQDN of
  the external provider (no scheme or path), e.g. `api.openai.com`,
  `bedrock.amazonaws.com`"* and requires `spec.auth`
  (simple/sigv4/oauth2, all required fields). This is genuinely built
  for authenticated third-party SaaS backends, not our own internal,
  already-unauthenticated OpenAI-compatible vLLM Service - confirming
  the chart's own suspicion rather than resolving it in `ExternalModel`'s
  favor.
- The alternative, `modelRef.kind: LLMInferenceService`, would deploy a
  second full GPU-bound serving stack (`serving.kserve.io/v1alpha2`,
  confirmed installed) - this cluster has one L4 per node, both already
  committed to the classic InferenceServices `qwen25-7b-instruct` and
  `embeddings`; not schedulable without more GPU capacity or migrating
  the existing model off first.
- `MaaSSubscription.spec.modelRefs[].name/namespace` requires an
  existing `MaaSModelRef`, so the governance-plane objects (subscription
  differentiation, `MaaSAuthPolicy` denial proof) cannot be exercised
  independently of resolving model publication first.

Not flipping `maas.enabled` while the only two schema-legal options are
either a real architecture misuse or a GPU capacity requirement neither
this session nor the repo's current hardware envelope can satisfy -
this is a genuine operator/user decision (accept a second GPU node, or
get an OpenShift AI 3.5 documentation confirmation that `ExternalModel`
intentionally supports internal cluster-local endpoints), not a
credential or code gap.
- **Target:** v0.2
- **Date:** 2026-08-11
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0114 decided that Zuno should become a business/context policy router in front of OpenShift AI Models-as-a-Service (MaaS) rather than reimplement product-native model publication, subscription, quota and API-access capabilities.

The repository has already moved part way toward this architecture:

- `DataScienceCluster.spec.components.kserve.modelsAsService.managementState` is enabled;
- a `maas-default-gateway` is rendered;
- Red Hat Connectivity Link and LeaderWorkerSet prerequisites are installed;
- local model serving and an independent Zuno AI Gateway already exist.

This is not yet a complete MaaS governance path. The repository does not yet declaratively demonstrate the subscription/authorization/API-key model for the Zuno personas, publish Zuno models through MaaS, integrate external-model governance, or prove usage observability and policy-router interoperability.

OpenShift AI 3.5 documents MaaS as a subscription-based governance plane. It provides `MaaSModelRef`, `MaaSSubscription` and `MaaSAuthPolicy` resources, self-service API keys, and OpenAI-compatible access. The current release train also exposes external OIDC authentication, vLLM-on-MaaS, usage/showback observability and external-model egress capabilities with lifecycle status that must be checked before use.

## Decision

Complete MaaS as the **model access and consumption governance plane**, while retaining Zuno as the stricter business/context policy layer defined by ADR-0114.

The target request path is:

```text
Agent Runtime
    |
    v
Zuno AI Policy Router
  - C1/C2/C3
  - sovereignty
  - task/model capabilities
  - quality/cost objective
  - external-provider eligibility
    |
    v
OpenShift AI MaaS
  - model publication
  - subscription/group access
  - MaaSAuthPolicy
  - API keys / compatible endpoint
  - quota/rate controls
  - usage metrics
    |
    +--> local KServe / vLLM / llm-d
    |
    +--> approved external model provider when lifecycle and policy permit
```

### Required v0.1 implementation

1. **Publish local models through MaaS** using the current supported model-reference mechanism and verify OpenAI-compatible access through the MaaS gateway.
2. **Define group-based subscriptions** aligned with Zuno/Keycloak personas and model entitlements rather than embedding model credentials in agent workloads.
3. **Define authorization policies** with `MaaSAuthPolicy` and prove denial for a group/model combination without entitlement.
4. **Exercise API-key lifecycle** for programmatic clients while browser agents continue to use trusted user identity through the Zuno application path.
5. **Integrate Keycloak/OIDC where supported and appropriate**, preserving the existing Keycloak group model and clearly tracking Technology Preview lifecycle where external OIDC is used.
6. **Integrate usage observability** so token/request/rate-limit metrics can be correlated with Zuno agent/user/model traces and future cost reporting.
7. **Evaluate external-model egress** for OpenAI/Anthropic through MaaS only when the targeted feature lifecycle is acceptable; C2/C3 and sovereignty policies remain enforced by Zuno before MaaS.
8. **Evaluate vLLM-on-MaaS / llm-d integration** for the local model-serving scenario without forcing Technology Preview features into the mandatory path if a GA-compatible alternative exists.

## Consequences

Zuno no longer needs to duplicate model subscription, token quota, API-key and model-publication features already provided by OpenShift AI. Its differentiation remains contextual business policy, classification, task reasoning and provider/model choice.

Some advanced MaaS capabilities in the targeted OpenShift AI 3.5 release train can be Technology Preview. The implementation must separate the **mandatory demonstrable MaaS core** from optional preview integrations so the demo can degrade gracefully.

## Security considerations

MaaS authorization is necessary but not sufficient. A user having access to a MaaS model never authorizes Zuno to send classified context to it.

Zuno must evaluate identity, C1/C2/C3, source restrictions and sovereignty **before** the request enters MaaS. API keys must be scoped, stored outside Git and never exposed to browser JavaScript or OKF bundles.

External-provider secrets are managed through the existing Vault/External Secrets path.

## Operational considerations

Observability must correlate at least:

- initiating Zuno user/agent/task where policy permits;
- Zuno-selected logical model/policy decision;
- MaaS subscription/model;
- token/request/rate-limit metrics;
- final local/external provider.

The deployment must include acceptance tests for authorized access, denied access, quota/rate-limit behavior and an unavailable-model/fallback path.

## Acceptance criteria

- At least one local Zuno model is published and consumable through MaaS.
- At least two identity groups demonstrate different `MaaSSubscription`/model access.
- `MaaSAuthPolicy` enforcement is proven by positive and negative tests.
- A Zuno Agent Runtime request traverses Zuno policy routing and MaaS end to end.
- Usage metrics can be correlated with a Zuno request trace.
- External-model egress, if enabled, is explicitly marked optional according to its OpenShift AI lifecycle and is blocked for classifications/policies that disallow it.

## References

- Red Hat OpenShift AI Self-Managed 3.5, **Govern LLM access with Models-as-a-Service**.
- Red Hat OpenShift AI Self-Managed 3.5 release notes for MaaS GA capabilities and Technology Preview features including external OIDC, vLLM-on-MaaS, observability and external-model egress.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0009](0009-separate-agent-runtime-from-ai-inference-gateway.md)
- [ADR-0019](0019-use-openshift-ai-model-serving-for-local-inference.md)
- [ADR-0020](0020-support-both-local-and-external-llm-providers.md)
- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)
- [ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md)
- [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md)
- [ADR-0114](0114-use-zuno-as-a-policy-router-in-front-of-openshift-ai-maas.md)
- [ADR-0317](0317-install-connectivity-link-and-leaderworkerset-operators.md)
