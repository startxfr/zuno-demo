# ADR-0112: Implement production-grade backup and recovery

- **Status:** Partially implemented (backup configuration, checks and runbook merged; restore drill pending, roadmap WP-13)
- **Target:** v0.1
- **Date:** 2026-08-14
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.1-roadmap entry
(`0100-v0.1-roadmap.md`) to a full record.

Define and implement backup/restore for all critical platform state:
PostgreSQL databases via the postgres operator's pgBackRest integration
(scheduled full + incremental backups to object storage, retention
configured in chart values); Vault via its storage-backend snapshot
mechanism on a scheduled Job; declarative configuration needs no separate
backup because Git is the source of truth (ADR-0022) — recovery for it is
redeploy-from-revision. Objectives: RPO <= 24h, RTO <= 4h for the demo
platform profile, recorded per service in
`docs/platform/backup-recovery.md` together with the tested restore
procedure. `make d1 check`/`make d0 check` paths assert last-backup
recency for their components. A restore drill must be executed and
documented before this ADR claims Implemented.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Security/Operational considerations,
Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0015](0015-use-postgresql-and-pgvector-as-the-persistent-data-platform.md)
- [ADR-0022](0022-use-gitops-managed-declarative-agent-tasks-and-policies.md)
- [ADR-0024](0024-use-vault-for-application-secrets.md)
- [ADR-0101](0101-provide-ha-for-shared-agent-platform-services.md)
- [ADR-0315](0315-dedicated-keycloak-postgresql-database.md)
