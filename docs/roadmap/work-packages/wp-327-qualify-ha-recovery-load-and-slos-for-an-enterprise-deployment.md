# WP-327: Qualify HA, recovery, load and SLOs for an enterprise deployment

- **State:** Not started (proposed by ADR-0625 on 2026-11-21; the ADR is `Proposed`, so this work package is not approved)
- **ADRs:** [ADR-0625](../../adr/0625-evolve-zuno-toward-a-modular-sovereign-enterprise-ai-platform.md)
- **Depends on:** none
- **Related:** [ADR-0101](../../adr/0101-provide-ha-for-shared-agent-platform-services.md), [ADR-0112](../../adr/0112-implement-production-grade-backup-and-recovery.md), [ADR-0624](../../adr/0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md)
- **Target:** v0.19
- **Estimated files touched:** ~8: an objectives page, run reports, procedures, this brief

## Goal

Measured availability, recovery, throughput and latency against objectives agreed before the qualification.

Horizon in the ADR's indicative roadmap: Day 90-180. The horizons count from the start of an approved initiative. They are not calendar dates.

## Proposed work

1. Agree the operational objectives first: availability, RPO, RTO, throughput, latency.
2. Validate HA, disaster recovery, backup and restore.
3. Run a representative load and read the capacity.
4. Write the operational procedures.

## Existing work it builds on

- The HA rules and failover drill of [ADR-0101](../../adr/0101-provide-ha-for-shared-agent-platform-services.md), the backup and restore drills of [ADR-0112](../../adr/0112-implement-production-grade-backup-and-recovery.md) and the stress campaign of [ADR-0624](../../adr/0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md).

## Acceptance

- The objectives are written before the runs.
- Each objective has a measured value and its date.
