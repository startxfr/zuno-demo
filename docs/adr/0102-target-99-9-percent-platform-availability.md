# ADR-0102: Target 99.9 percent platform availability

- **Status:** Partially implemented (HA chart mechanics, SLO definition and alert rules merged; failover drill and live measurement pending, roadmap WP-12)
- **Target:** v0.1
- **Date:** 2026-08-14
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.1-roadmap entry
(`0100-v0.1-roadmap.md`) to a full record.

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
