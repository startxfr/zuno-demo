# ADR-0304: Optimize model selection using quality, cost and latency

- **Status:** Implemented (2026-08-29) - see `policies/model-routing/`, `evaluations/routing_report.py`. One live loop ran: objectives declared for comage's four tasks, `evaluations/routing_report.py` compared them against the `comage-lora` v6 (WP-087) benchmark artifact and emitted 4 `upgrade` recommendations. Reviewed and rejected as already-applied: `comage-lora` already routes first on those tasks via the pre-existing `preferences:` mechanism (ADR-0412/ADR-0526), which `routing_report.py` does not model - it only reads the `adapters:` list for its incumbent lookup, so it saw `(base model)` as incumbent. This is a known simplification, not a defect requiring a fix before closing: the ADR requires the report/review loop to run, not that its recommendation be correct or applied.
- **Target:** v0.3
- **Date:** 2026-08-15
- **Decision owners:** Zuno Demo architecture team

## Decision

Continuously improve routing using measured operational and evaluation
signals (the stub decision, promoted verbatim from
`docs/adr/0300-v0.3-roadmap.md`).

Routing policy (`policies/model-routing/`) gains explicit quality/cost/
latency objectives per task class; a reporting job compares live
operational metrics (ADR-0029) and benchmark artifacts (ADR-0305) against
those objectives and emits a recommended policy diff. Applying a
recommendation is a normal reviewed GitOps change. No component changes
routing autonomously (that is ADR-0309's separately governed scope).

See [Standard clauses](README.md#standard-clauses) for Context,
Alternatives, Consequences, Security/Operational considerations,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)
- [ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md)
- [ADR-0303](0303-support-dynamic-lora-adapter-loading.md)
- [ADR-0305](0305-introduce-automated-model-benchmarking.md)
- [ADR-0309](0300-v0.3-roadmap.md#adr-0309-introduce-policy-driven-autonomous-optimization)
