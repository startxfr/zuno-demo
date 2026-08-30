# ADR-0309: Introduce policy-driven autonomous optimization

- **Status:** Implemented (2026-08-30) - see `policies/optimization/`. Autonomy enabled live on the cluster (cache-TTL/cache-enabled scopes; routing scope stays structurally inert, `pre_approved_equivalents: []`); one full tune-evaluate cycle observed (`cache_ttl` 3600s→7200s, clean outcome reported, no rollback); one rollback forced (`cache_ttl` 7200s→1800s, error_rate 0.10 breach reported) - both open audit entries auto-reverted, confirming `report_outcome()` rolls back every open action on a trigger breach, not just the most recent one. Operator sign-off given 2026-08-30. Routing scope stays disabled in practice (no pre-approved equivalents exist yet) pending a future reviewed PR.
- **Target:** v0.3
- **Date:** 2026-08-15
- **Decision owners:** Zuno Demo architecture team

## Decision

Allow bounded automated tuning of routing, caching and model choices
under explicit governance (the stub decision, promoted verbatim from
`docs/roadmap/adr-decisions-v0.3.md`).

A governance policy (`policies/optimization/optimization-policy.yaml`)
enumerates exactly which parameters may be auto-tuned (initial scope:
semantic-cache TTL/enablement per model within declared ranges; routing
choices between *pre-approved equivalent* model/adapter candidates
only), the allowed ranges, the evaluation window, and rollback triggers
(quality-floor or error-rate breach reverts automatically). Every
automated change is recorded with its evidence and is reversible;
classification and authorization policies are never auto-tunable; a kill
switch disables all autonomy in one configuration change. Anything
outside the enumerated scope remains a human-reviewed PR (ADR-0304).

See [Standard clauses](README.md#standard-clauses) for Context,
Alternatives, Consequences, Security/Operational considerations,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0104](0104-introduce-controlled-semantic-caching.md)
- [ADR-0304](0304-optimize-model-selection-using-quality-cost-and-latency.md)
- [ADR-0305](0305-introduce-automated-model-benchmarking.md)
