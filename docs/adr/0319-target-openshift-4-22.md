# ADR-0319: Target OpenShift 4.22

- **Status:** Proposed
- **Target:** v0
- **Date:** 2026-08-11
- **Decision owners:** Zuno Demo architecture team

## Decision

Supersede ADR-0002's OpenShift Container Platform version target: 4.20 → 4.22. OpenShift AI stays at 3.5 EA2 - unchanged, not a party to this decision.

OpenShift AI operator/runtime compatibility with 4.22 must be re-verified through this repo's existing discovery mechanisms (ADR-0047, ADR-0048 - channel/runtime discovery at deployment time), not assumed from the 4.20 baseline.

Supersedes ADR-0002.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution and Related ADRs.

## Related ADRs

- [ADR-0002](0002-use-openshift-4-20-and-openshift-ai-3-5-ea2-for-the-mvp.md) (superseded by this ADR)
- [ADR-0047](0047-manage-the-complete-openshift-ai-prerequisite-lifecycle.md)
- [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md)
