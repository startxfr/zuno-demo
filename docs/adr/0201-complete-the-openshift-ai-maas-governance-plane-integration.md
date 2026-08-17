# ADR-0201: Complete the OpenShift AI MaaS governance plane integration

- **Status:** Partially implemented (local model published and consumable through MaaS, governance pairing proven live; API-key lifecycle, usage-metric correlation and the AuthPolicy denial proof are still outstanding, see 2026-08-18 note)

## Implementation note (2026-08-18)

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
