# ADR-0102: Target 99.9 percent platform availability

- **Status:** Implemented - see `docs/platform/slo.md`. Measured live 2026-08-18 (roadmap WP-12): 100.000% at the BFF boundary over the trailing 24h window (73,894 requests, zero 5xx) with both burn-rate alerts evaluating `health: ok` on the cluster Prometheus. Closed on a short measured window by explicit operator decision (2026-08-18); the 30-day series continues to accumulate (complete ~2026-09-17) and the window length is recorded honestly in `slo.md`.
- **Target:** v0.1
- **Date:** 2026-08-14
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.1-roadmap entry
(`../roadmap/adr-decisions-v0.1.md`) to a full record.

Adopt 99.9% monthly availability as the industrialized objective for the
user-facing agent path (frontend -> BFF -> Agent Runtime -> AI Gateway ->
model). The SLO is defined in `docs/platform/slo.md` with its measurement
query (successful request ratio at the BFF boundary), error-budget
policy, and alerting rules shipped as PrometheusRule resources in the
observability chart. The objective is a measured target: the ADR is
implemented when the SLO is defined, measured and alerted on a live
cluster — not when the number is merely written down.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Security/Operational considerations,
Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md)
- [ADR-0101](0101-provide-ha-for-shared-agent-platform-services.md)
