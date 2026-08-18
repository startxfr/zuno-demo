# Backup and recovery (ADR-0112)

Objectives for the demo platform profile: **RPO <= 24h, RTO <= 4h**, per
service. ADR-0112 is `Implemented` only once a restore drill has actually
been executed and its results recorded here (see each section's "Restore
drill" placeholder) — not when the mechanism merely exists.

| Service | Mechanism | Schedule | RPO | RTO target | Restore drill executed? |
|---|---|---|---|---|---|
| PostgreSQL (`zuno-postgresql`) | pgBackRest via Crunchy PGO (`gitops/charts/postgresql`) | full weekly (Sun 02:00) + differential daily (02:00) | <= 24h | <= 4h | Not yet — operator follow-up |
| Vault (`zuno-vault`) | CSI VolumeSnapshot of the data PVC (`gitops/charts/vault`, disabled by default) | daily (04:00) | <= 24h | <= 4h | Not yet — operator follow-up |
| Declarative configuration (GitOps: charts, ADRs, policy) | None needed — Git is the source of truth (ADR-0022) | N/A | 0 (every commit is a recovery point) | Time to `argocd app sync` from a known-good revision | N/A — no data to restore, only re-apply |

## PostgreSQL

### Backup mechanism

`gitops/charts/postgresql`'s `PostgresCluster` CR (`templates/postgrescluster.yaml`)
already configures two pgBackRest repos:

- **repo1** (always active): a local PVC (`backups.storageSize`, default
  500Gi), full backup weekly (`0 2 * * 0`) and differential backup daily
  (`0 2 * * 1-6`), 4 full backups retained (`repo1-retention-full: "4"`) —
  worst-case data loss is well inside the 24h RPO objective.
- **repo2** (opt-in, `backups.s3.enabled`, default `false`): off-cluster
  S3, full backup weekly (`0 3 * * 0`). Bucket/region/endpoint are chart
  values; credentials are synced by Vault/ExternalSecrets
  (`backups.s3.secretName`), never inline.

Confirmed live, 2026-08-14: repo1 has a real completed `full` backup
(`oc get postgrescluster zuno-postgresql -n zuno-data -o
jsonpath='{.status.pgbackrest}'`, `scheduledBackups[0].succeeded: 1`).
`ansible/roles/postgresql/tasks/precheck.yml` reports the most recent
backup's age against the 24h RPO objective on every `make d0 check
postgresql` / `make d1 check` (diagnostic only — a freshly provisioned
cluster legitimately has no backup yet).

### Restore procedure (point-in-time, to a scratch cluster/namespace)

PGO restores by creating a **new** `PostgresCluster` whose
`spec.dataSource.postgresCluster` pre-populates its data directory from
an existing cluster's pgBackRest repo — never destructively in place on
the live cluster.

1. Create a scratch namespace (e.g. `zuno-data-restore-drill`) with the
   same governance as `zuno-data` (`gitops/charts/namespaces`).
2. Apply a new `PostgresCluster` there, named differently from
   `zuno-postgresql` (e.g. `zuno-postgresql-restore-test`), with:
   ```yaml
   spec:
     dataSource:
       postgresCluster:
         clusterName: zuno-postgresql
         clusterNamespace: zuno-data
         repoName: repo1
         # Point-in-time restore: options passes pgBackRest's own
         # --type=time/--target flags. Omit `options` entirely to
         # restore the latest available backup instead.
         options:
           - --type=time
           - --target="2026-08-14 09:00:00+00"
   ```
   (every other required field — `postgresVersion`, `instances`,
   `image`, etc. — matches the source cluster's own spec, since PGO
   needs a fully-specified new cluster, not a diff.)
3. Wait for the new cluster's `status.phase` to report `Ready` and
   `status.pgbackrest.restore` to report completion.
4. Verify data: connect via the new cluster's own `-pguser-<owner>`
   Secret and confirm the expected rows/schema exist as of the target
   time.
5. Record: wall-clock time from step 2 to step 4 passing (the RTO
   measurement), and delete the scratch cluster/namespace afterward.

**Restore drill executed: 2026-08-18 (roadmap WP-13).** A scratch
cluster `zuno-postgresql-restore-test` was created in `zuno-data`
itself (PGO watches cluster-wide, so a separate namespace adds nothing
- procedure correction: same-namespace/different-name is the simpler
equivalent of step 1) with `dataSource.postgresCluster` on `repo1` and
no `options` (latest backup). Results:

- pgBackRest restore finished and the instance reported Ready
  **203 seconds** after `oc apply`; data verified at ~250s wall clock -
  RTO ≤ 4h met with ~57x margin.
- Data verification: `rag-tech`'s `rag.document_embeddings` matched the
  live primary exactly - 38,690 rows with identical
  `max(created_at) = 2026-08-18T14:26:31Z`, a timestamp *after* the
  02:00 differential backup: pgBackRest replayed archived WAL to the
  end, so effective RPO is near-continuous, not the 24h backup cadence.
- The restored cluster carries one extra database named after itself
  (`zuno-postgresql-restore-test`, PGO's default bookkeeping DB) -
  expected, not drift.
- Also verified this pass: `repo2` (S3, off-cluster) reports `ok` with
  a real full backup landed 2026-08-16T03:02Z, credentials synced from
  Vault `postgresql/backup-s3` - the Decision's object-storage clause
  is live, not just chart wiring.

The scratch cluster was deleted after verification.

## Vault

### Backup mechanism

Vault's storage backend is `file` (`gitops/charts/vault/values.yaml`'s
`standalone.config`), not Raft — there is no `vault operator raft
snapshot` API. Instead, `gitops/charts/vault/templates/cronjob-backup.yaml`
(disabled by default, `backup.enabled`) creates a timestamped CSI
`VolumeSnapshot` of the `data-zuno-vault-0` PVC daily and prunes to the
newest N (`backup.retentionCount`, default 7). Confirmed live,
2026-08-14: `csi-aws-vsc` (driver `ebs.csi.aws.com`) matches the PVC's
`gp3-csi` provisioner. `ansible/roles/vault/tasks/precheck.yml` reports
the most recent ready snapshot's age against the 24h RPO objective, same
diagnostic-only pattern as PostgreSQL's check.

### Restore procedure

1. Provision a new PVC from the snapshot (CSI `dataSource` pointing at
   the chosen `VolumeSnapshot`, same storage class):
   ```yaml
   apiVersion: v1
   kind: PersistentVolumeClaim
   metadata:
     name: data-zuno-vault-restore-test-0
     namespace: zuno-vault-restore-drill
   spec:
     storageClassName: gp3-csi
     accessModes: ["ReadWriteOnce"]
     resources:
       requests:
         storage: 2Gi
     dataSource:
       name: <chosen VolumeSnapshot name>
       kind: VolumeSnapshot
       apiGroup: snapshot.storage.k8s.io
   ```
2. Deploy a scratch Vault instance (same chart, different release name/
   namespace, `dataStorage` pointed at the restored PVC instead of a
   fresh one — mirror `gitops/charts/vault`'s own `standalone.config`).
3. Unseal it with the same unseal key(s)/root token the live Vault uses
   (this is a filesystem-level restore, not a fresh `vault operator
   init` — the restored data directory already holds the sealed keyring).
4. Verify: read a known secret path and confirm the value matches
   what was current as of the snapshot's creation time.
5. Record: wall-clock time from step 2 to step 4 passing, then delete
   the scratch instance/PVC/namespace.

**Restore drill executed: 2026-08-18 (roadmap WP-13).** Restored from
the live `vault-data-20260818073439` snapshot (10h old at drill time,
created by the enabled daily `vault-backup` CronJob) into a scratch PVC
+ single-pod Vault in `zuno-vault` (procedure correction: a bare pod
with the same image and a minimal file-storage HCL is sufficient - a
full second chart release, step 2's suggestion, is unnecessary for the
drill). Results:

- Pod Running at T+16s, unsealed with the **live** unseal key at
  T+23s (`Initialized: true` straight from the restored filesystem -
  no re-init, proving the keyring restored intact), known secret
  (`zuno/confluence/technical`, field `email`) read and matched the
  live value at **T+39s** wall clock. RTO ≤ 4h met with ~370x margin.
- RPO: the newest ready snapshot was 10h old (daily 04:00 schedule,
  `retentionCount: 7`), inside the 24h objective.

The scratch pod/PVC/ConfigMap were deleted after verification.

## Declarative configuration (GitOps state)

No separate backup exists or is needed: every chart, ADR, policy and
manifest in this repository is the source of truth (ADR-0022), and Git
itself is the backup — every commit is a recovery point, and GitHub
(ADR-0004) is the canonical, already-replicated store. "Recovery" for
this category is `argocd app sync` (or `make d0|d1 install`) against a
known-good revision, not a restore procedure in the backup/RTO sense.
The only thing this category cannot recover is *data* — which is exactly
what the PostgreSQL/Vault sections above cover.

## Operator follow-up (not executable by the model)

1. ~~Provision the PostgreSQL backup object-storage bucket + credentials,
   enable `backups.s3.enabled`, sync, and confirm repo2 backups run~~ -
   done before 2026-08-18: `zuno-postgresql-backup-s3` ExternalSecret
   `Ready=True`, live cluster carries `repo1 repo2`, `pgbackrest info`
   reports repo2 `ok` with a full backup landed 2026-08-16T03:02Z.
2. ~~Enable `gitops/charts/vault`'s `backup.enabled`, sync, and confirm
   the `vault-backup` CronJob creates a `readyToUse` VolumeSnapshot~~ -
   done: CronJob live (`0 4 * * *`), newest snapshot
   `vault-data-20260818073439` `readyToUse: true`.
3. ~~Execute both restore drills above~~ - done 2026-08-18, results
   recorded in the two "Restore drill executed" sections above
   (PostgreSQL ~250s to verified data, Vault 39s to verified secret,
   both against RTO ≤ 4h).
