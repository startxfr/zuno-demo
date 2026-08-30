# ADR-0104: Introduce controlled semantic caching

- **Status:** Implemented - see `components/ai-gateway/app/semantic_cache.py`, `platform/ai-gateway/provider-routing.yaml`'s `cache_enabled` field.
- **Target:** v0.1
- **Date:** 2026-08-14
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.1-roadmap entry
(`../roadmap/adr-decisions-v0.1.md`) to a full record.

Add an opt-in semantic cache in the AI Gateway, stored in the existing
platform Redis. The cache key includes, at minimum: normalized prompt
embedding bucket, model identity, and the full authorization context -
user subject (or an authorization-equivalence hash of groups +
entitlements), effective classification, and task identity. A cache
entry is only ever served to a request whose authorization context is
identical; classification is never downgraded by a cache hit; C2/C3
content follows the same external-egress restrictions cached or not
(ADR-0035). Cache TTL and enablement are per-model configuration in
the ai-gateway chart values, default off. Hits/misses are traced and
counted in the existing cost/usage instrumentation (ADR-0029).

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Security/Operational considerations,
Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)
- [ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md)
- [ADR-0034](0034-compute-effective-classification-from-the-complete-context.md)
- [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md)
