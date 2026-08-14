# ADR-0114: Use Zuno as a policy router in front of OpenShift AI MaaS

- **Status:** Partially implemented - MaaS adapter prototype and coverage comparison merged (`components/ai-gateway/app/maas_adapter.py`, `docs/roadmap/evidence/adr-0114-maas-coverage.md`); live MaaS verification and cutover decision pending (WP-27)
- **Target:** v0.1
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team
- **Renumbered:** formerly ADR-0049 (2026-08-13 roadmap reorganization)

## Context

`components/ai-gateway` currently owns provider routing, fallback and classification eligibility, with future plans for budgets/quotas. OpenShift AI 3.5 MaaS provides a product-native model access plane including model publication, subscriptions, authorization policies, usage controls and local/external model abstractions. Reimplementing those functions in Zuno increases duplicated responsibility.

## Decision

Evolve the custom AI Gateway into a Zuno Model Policy Router. Zuno retains business-aware decisions such as C1/C2/C3, sovereignty, task requirements, quality tier, cost objective and semantic complexity. The selected request is then sent through OpenShift AI MaaS for model access, subscription/quota enforcement, provider publication and compatible inference endpoints. Local models use OpenShift AI serving (KServe/vLLM/llm-d as appropriate); approved external providers use MaaS external-model capabilities when supported.

## Consequences

Zuno differentiates on business/context policy instead of duplicating the OpenShift AI model access plane. Migration requires a stable adapter so Agent Runtime is not tied directly to changing MaaS APIs during EA/TP stages.

## Security considerations

Zuno classification/source restrictions always remain a stricter outer policy. MaaS authorization must not be treated as sufficient permission to externalize C2/C3 data.

## Operational considerations

Prototype the MaaS adapter behind the existing OpenAI-compatible model client and compare feature coverage before removing current gateway capabilities.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Implementation state, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0009](0009-separate-agent-runtime-from-ai-inference-gateway.md)
- [ADR-0019](0019-use-openshift-ai-model-serving-for-local-inference.md)
- [ADR-0020](0020-support-both-local-and-external-llm-providers.md)
- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)
- [ADR-0034](0034-compute-effective-classification-from-the-complete-context.md)
- [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md)
