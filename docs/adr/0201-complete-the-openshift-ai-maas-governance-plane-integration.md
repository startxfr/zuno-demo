# ADR-0201: Complete the OpenShift AI MaaS governance plane integration

- **Status:** Partially implemented (governance manifests, key lifecycle, correlation and guards merged; live MaaS verification pending)
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
