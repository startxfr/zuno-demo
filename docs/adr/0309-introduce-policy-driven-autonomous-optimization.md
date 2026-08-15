# ADR-0309: Introduce policy-driven autonomous optimization

- **Status:** Partially implemented (governance policy, bounded tuner, rollback and kill switch merged; live cycle pending)
- **Target:** v0.3
- **Date:** 2026-08-15
- **Decision owners:** Zuno Demo architecture team

## Decision

Allow bounded automated tuning of routing, caching and model choices
under explicit governance (the stub decision, promoted verbatim from
`docs/adr/0300-v0.3-roadmap.md`).

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
