# ADR-0112: Implement production-grade backup and recovery

- **Status:** Implemented - see `docs/platform/backup-recovery.md`. Both restore drills executed live 2026-08-18 (roadmap WP-13): PostgreSQL scratch-cluster restore Ready in 203s with data verified identical to the live primary (38,690 `rag.document_embeddings` rows, WAL replayed to the same-day timestamp), Vault snapshot restore unsealed with the live key and a known secret verified at 39s wall clock. Object-storage clause live: pgBackRest repo2 (S3) reports `ok` with a real full backup landed 2026-08-16. RPO ≤ 24h / RTO ≤ 4h both met with wide margin; drill records and procedure corrections in the runbook.
- **Target:** v0.1
- **Date:** 2026-08-14
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.1-roadmap entry
(`../roadmap/adr-decisions-v0.1.md`) to a full record.

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
