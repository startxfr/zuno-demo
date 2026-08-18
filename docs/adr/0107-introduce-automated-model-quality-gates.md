# ADR-0107: Introduce automated model quality gates

- **Status:** Partially implemented (gate runner, CI wiring and LMEvalJob manifests merged; GPU cluster runs pending, roadmap WP-10). Updated 2026-08-18: the blocking half of the acceptance bar is now discharged live - `make d1 check agents` (the real ADR-0053 acceptance gate, `evaluations/tekos/run_acceptance_gate.py` against the live cluster) ran twice, reproducibly, and correctly BLOCKED promotion both times (65-70% scenario pass rate against the 75% threshold, both mandatory-check layers evaluated for real). A companion regression was found and fixed along the way: PgBouncer held a stale cached auth failure for the `agentcheckpoints` role after this session's WP-12 PostgreSQL failover drill; restarting the PgBouncer pods picked up the current credential and flipped the mandatory security-check layer from 6/7 to 7/7. The passing-promotion half remains open - not fabricated - blocked on a separate, genuine platform gap (see ADR-0108's note): still `Partially implemented`.
- **Target:** v0.1
- **Date:** 2026-08-14
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.1-roadmap entry
(`0100-v0.1-roadmap.md`) to a full record.

A model or agent change may only be promoted when the target agent's
ADR-0027 acceptance suite passes at the ADR-0028 threshold (75%) against
the candidate configuration, and no per-scenario security check
regresses. The gate consumes the machine-readable output of
`evaluations/<agent>/run_acceptance_gate.py` and blocks in CI for
repo-declared model/routing changes; cluster-side promotions consume the
same artifact via the Day 1 check path. Thresholds are data (per-agent
configuration), not code.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Security/Operational considerations,
Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0027](0027-evaluate-every-agent-with-twenty-acceptance-scenarios.md)
- [ADR-0028](0028-require-a-seventy-five-percent-evaluation-threshold.md)
- [ADR-0053](0053-make-make-check-an-end-to-end-acceptance-and-security-gate.md)
- [ADR-0108](0108-automate-model-evaluation-with-lm-eval.md)
