# WP-13: Backup and recovery (promotes ADR-0112)

- **State:** Done (2026-08-18 — operator follow-up executed live: PostgreSQL restore drill to a scratch cluster (`dataSource.postgresCluster` on repo1, Ready in 203s, `rag.document_embeddings` verified identical to the live primary at 38,690 rows with WAL replayed to a same-day timestamp) and Vault snapshot restore drill (scratch pod from `vault-data-20260818073439`, unsealed with the live key, known secret verified at 39s). repo2 (S3) confirmed `ok` with a real full backup landed 2026-08-16 — the object-storage clause of ADR-0112's Decision is live. Drill records + procedure corrections in docs/platform/backup-recovery.md. Prior state for the record: Repo work merged (2026-08-14 - ADR-0112 promoted to a full record. PostgreSQL backups turned out to already be fully configured and actively running (pgBackRest repo1 local PVC, full weekly + differential daily, confirmed live via a real completed backup) - only the Day 1 recency check was missing, added to `ansible/roles/postgresql/tasks/precheck.yml` (diagnostic only). Vault's `file` storage backend has no `raft snapshot` API, so `gitops/charts/vault/templates/cronjob-backup.yaml` (disabled by default) creates scheduled CSI VolumeSnapshots instead - schema and VolumeSnapshotClass availability confirmed via `oc explain`/`oc get volumesnapshotclass` against the live cluster; a matching recency check was added to `ansible/roles/vault/tasks/precheck.yml`. Both new ansible Jinja2 expressions were verified correct with a standalone `ansible-playbook` run against real/synthetic data before landing, catching two real bugs (a non-boolean conditional, a `now(utc=true)` datetime-vs-string mismatch) pre-merge. `docs/platform/backup-recovery.md` documents per-service RPO/RTO objectives and the tested-procedure runbook (PostgreSQL restore-to-scratch-cluster via `dataSource.postgresCluster`, Vault restore-from-snapshot). ADR-0112 stays Partially implemented pending the restore drill below.))
- **ADRs:** ADR-0112 (Proposed -> To be implemented -> Partially implemented -> Implemented)
- **Depends on:** WP-00 (done)
- **Estimated files touched:** ~6

> Execute this brief as a standalone task from the repository root.

## Goal

Promote stub ADR-0112, then implement backups for the platform's stateful
services — PostgreSQL (pgBackRest via the operator), Vault snapshots — plus a
restore runbook and a Day 1 check asserting backup recency. The restore
drill on a real cluster is the operator part.

## ADR references

Stub origin (`docs/roadmap/adr-decisions-v0.1.md`): define backup, restore and
recovery objectives for PostgreSQL, configuration and critical state.

Related: ADR-0015 (PostgreSQL platform), ADR-0024 (Vault), ADR-0022 (Git as
config source — GitOps state needs no separate backup, record that
explicitly), ADR-0101/WP-12. Acceptance criteria: Standard clauses.

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- Read: `gitops/charts/postgresql/` (identify the operator — expect Crunchy
  PGO given `zuno-postgresql` cluster naming and ADR-0315 — and where backup
  config would attach to the cluster spec), `gitops/charts/vault/` +
  `ansible/roles/vault/` (deployment mode; snapshot mechanism depends on
  storage backend), `ansible/roles/postgresql/tasks/` (check-task style).

## Step 0 — ADR promotion

1. Create `docs/adr/0112-implement-production-grade-backup-and-recovery.md`
   (standard header, `- **Status:** To be implemented`, Target `v0.1`) with
   this Decision:

   > Promote this decision from a one-line v0.1-roadmap entry
   > (`../adr-decisions-v0.1.md`) to a full record.
   >
   > Define and implement backup/restore for all critical platform state:
   > PostgreSQL databases via the postgres operator's pgBackRest
   > integration (scheduled full + incremental backups to object storage,
   > retention configured in chart values); Vault via its storage-backend
   > snapshot mechanism on a scheduled Job; declarative configuration needs
   > no separate backup because Git is the source of truth (ADR-0022) —
   > recovery for it is redeploy-from-revision. Objectives: RPO <= 24h,
   > RTO <= 4h for the demo platform profile, recorded per service in
   > `docs/platform/backup-recovery.md` together with the tested restore
   > procedure. `make d1 check`/`make d0 check` paths assert last-backup
   > recency for their components. A restore drill must be executed and
   > documented before this ADR claims Implemented.

   Standard-clauses pointer + Related ADRs (0015, 0022, 0024, 0101, 0315).
2. `docs/roadmap/adr-decisions-v0.1.md`: KEEP heading; body →
   `Promoted to a full decision record: see [ADR-0112](0112-implement-production-grade-backup-and-recovery.md) (WP-13 implementation).`
3. `docs/adr/README.md`: direct link + `To be implemented`.
4. `python3 platform/docs/check_docs.py` exits 0.

## Repo changes (step by step)

1. PostgreSQL: enable/configure the operator's backup section in
   `gitops/charts/postgresql` values + templates (schedules, retention,
   object-storage bucket reference via External Secrets — never inline
   credentials).
2. Vault: scheduled snapshot Job manifest in `gitops/charts/vault`
   (mechanism per the deployment mode found in preconditions), hardened per
   `check_workload_hardening.py`.
3. Checks: extend `ansible/roles/postgresql` and `ansible/roles/vault` check
   tasks to assert a sufficiently recent successful backup exists (follow
   each role's existing check style).
4. Write `docs/platform/backup-recovery.md`: per-service RPO/RTO table,
   backup mechanism, and step-by-step restore procedures (PostgreSQL
   point-in-time restore via operator; Vault snapshot restore; GitOps
   redeploy-from-revision).

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set.
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).
- Live data or cluster state (this WP is manifests + docs only).

## Acceptance checks (run from repo root; all must pass)

- `helm lint gitops/charts/postgresql gitops/charts/vault` and `helm template` renders the backup resources
- `python3 platform/security/check_workload_hardening.py` (exit 0)
- `ansible-playbook ansible/playbooks/day0_check.yml --syntax-check`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`
- `test -f docs/platform/backup-recovery.md`

## Operator / human follow-up (not executable by the model)

1. Operator: provision the backup object-storage bucket + credentials
   (Vault/ESO path), sync, and confirm scheduled backups run.
2. Operator: execute one full restore drill per mechanism (PostgreSQL
   restore to a scratch cluster/namespace; Vault snapshot restore), timing
   it against the RTO, and record results in
   `docs/platform/backup-recovery.md` — mandatory before Implemented.

## Status updates (then re-run check_docs.py)

- After repo merge: ADR-0112 →
  `Partially implemented (backup configuration, checks and runbook merged; restore drill pending)`;
  index row to match; tracker → `Operator pending`.
- After the drill: ADR-0112 →
  `Implemented - see \`docs/platform/backup-recovery.md\`.`; index row
  `Implemented`; tracker → `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- Cross-region/DR replication (new ADR territory).
- Application-level export tooling.
