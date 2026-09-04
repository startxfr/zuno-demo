# WP-131: Execute ADR-0546's cross-cluster source bucket and per-cluster S3 convention

- **State:** Not started (P0-a, P0-b and the P1 `path` parameter landed 2026-09-04; steps 1 (mlflow) and 2 (mariadb) are also landed and live-verified on demo222; aap, mlops, openshift-ai, rag-ingestion and the postgresql P2–P14 sequence remain)
- **ADRs:** [ADR-0546](../../adr/0546-introduce-a-cross-cluster-source-bucket-and-per-cluster-s3-bucket-convention.md)
  (`Accepted` 2026-09-04 — this WP satisfied its acceptance criterion 2),
  [ADR-0517](../../adr/0517-redeploy-the-full-platform-from-scratch-on-a-new-demo333-cluster.md) (B12),
  [ADR-0547](../../adr/0547-parameterize-every-cluster-specific-value-in-ansible.md) (clauses 2 and 4)
- **Depends on:** manual AWS bucket and IAM provisioning — there is no AWS IaC in
  this repository. **Also on P0-a and P0-b below**, two pre-existing defects found
  while planning this WP, one of which is an active data-loss trap.
- **Related:** [WP-130](wp-130-fresh-cluster-readiness-gate.md) (probe P6 detects
  B12 until this lands), [WP-118](wp-118-demo333-portability-blockers.md) (closed
  the one S3 gap it could — B8 — and left bucket sharing undecided),
  [WP-079](wp-079-rhoai-monitoring-traces.md) (the live IAM-scoping bug this WP's
  per-consumer identities prevent)

## Goal

Give each cluster its own S3 buckets, and put the data that seeds *any* cluster
in one shared source bucket. Until that exists, a second cluster installed from
this repository writes its RAG ingestion outputs, pgBackRest and MariaDB backups,
RHOAI traces and MLflow artifacts into the first cluster's buckets — ADR-0517's
B12, the only blocker on that list which damages the **existing** cluster.

## What the live inventory changed (read-only, 2026-09-04)

ADR-0546 was written from a static read. Measuring the buckets moved the work:

- **`models/` is 164.6 GB across 226 objects** — 99% of everything that moves.
  Everything else fits in ~850 MB.
- **`zuno-aap-hub` is empty.** Configuration change, no migration.
- **`mlflow-artifacts/` does not exist yet**, so MLflow is the cheapest cutover
  and the natural rehearsal.
- **pgBackRest writes under `pgbackrest/repo2/`**, not the bucket root.
- **The SXA dump exists twice**: `zuno-demo-sxa-corpus` (authoritative,
  2026-08-23) and `zuno-demo-rag-corpus/sxa_data/` (2026-08-21) with **no
  consumer anywhere** — an orphan, not a migration source.
- **`zuno-corpus` is in `us-east-1`**, the only bucket outside `eu-west-2`.
- Buckets are SSE-S3 (`AES256`, bucket keys on), **no versioning**, **no
  lifecycle rules** — so nothing is silently expiring, and nothing is protected
  against an accidental overwrite either.

## Execution record — the copies, 2026-09-04

The six buckets exist and every cross-cluster copy has been made and verified.

| Bucket | Objects | Bytes | Versioning |
|---|---|---|---|
| `zuno-demo-sources` | 231 | 164,721,928,015 | **Enabled** + `expire-noncurrent-30d` |
| `zuno-demo222-mlops` | 307 | 674,847,712 | off, deliberately |
| `zuno-demo222-backups` | 6 | 38,699,588 | off, deliberately |
| `zuno-demo222-data` | 0 | 0 | off |
| `zuno-demo222-traces` | 0 | 0 | off |
| `zuno-demo222-aap-hub` | 0 | 0 | off |

All six: `eu-west-2`, SSE-S3 `AES256`, all four public-access blocks on,
`BucketOwnerEnforced`. `zuno-demo-sources`'s 231 objects are exactly
226 (`models/`) + 2 (`sxa-dump/`) + 3 (`training-corpus/`).

The three empty buckets are **empty by design**, not incomplete: the RAG corpus
is re-ingested rather than copied (ADR-0546 clause 1), RHOAI traces are knowingly
not carried over, and `zuno-aap-hub` was itself empty.

Completeness was proven per copy with `aws s3 sync --dryrun`, which printed
nothing for all five. On its own that is not evidence — a dryrun that silently
failed prints nothing too — so the probe was exercised against an empty
destination first and did list the work, which is what makes the empty results
mean something.

### The probe idiom that produced a false "ABSENT"

Checking the new buckets with

```bash
aws s3api head-bucket --bucket "$B" 2>/dev/null && echo "existe" || echo "ABSENT"
```

reported three buckets ABSENT that the console showed plainly. `head-bucket`
requires `s3:ListBucket`, and without it S3 answers **403 Forbidden**, not 404.
The shell still had `AWS_PROFILE=zuno-migration` exported, and that identity's
policy names only the five buckets involved in the copies. `2>/dev/null` then
threw away the one word — Forbidden — that distinguished a permission denial
from a missing bucket.

**Rule for every probe in this WP: never discard stderr, and never collapse a
non-zero exit into a single meaning.** Use:

```bash
for B in ...; do
  printf "%-24s " "$B"
  OUT=$(aws s3api head-bucket --bucket "$B" 2>&1) && echo "OK" \
    || echo "FAIL :: $(echo "$OUT" | tr '\n' ' ' | cut -c1-160)"
done
```

This is the same failure shape as P0-a below, and the same one recorded for
`changed=0` inertia proofs: a silent probe and a broken probe are
indistinguishable unless you ask what the output would be if the mechanism were
dead.

## P0 — two pre-existing defects, to fix BEFORE any migration

Neither is caused by this WP. Both block it, and the first is live today.

### P0-a — the S3 backup check has always reported "no backup"

`ansible/roles/postgresql/tasks/check_s3_backup.yml` sets
`PGBACKREST_REPO2_{TYPE,S3_BUCKET,S3_ENDPOINT,S3_REGION}` and **never
`PGBACKREST_REPO2_PATH`**; `repo-path` appears nowhere in the tree. pgBackRest
defaults to `/var/lib/pgbackrest` while PGO writes `/pgbackrest/repo2`. Verified
live: `s3://zuno-data-pgbackups/var/` **does not exist**, while
`pgbackrest/repo2/backup/db/` holds three full backups (2026-08-16, -23, -30)
and their `backup.info`.

`pgbackrest info` on an empty prefix returns `[]` and exits 0, so the Job
*succeeds* with `_postgresql_s3_has_backup: false`. Per
`ansible/roles/postgresql/tasks/install.yml`, auto-restore fires only when that
is true and no `PostgresCluster` exists — so **any rebuild of `zuno-postgresql`
bootstraps an empty database** while announcing a genuinely fresh environment,
and `make d3 restore postgresql` refuses to restore a backup that exists.

**Fixed 2026-09-04.** `PGBACKREST_REPO2_PATH` now comes from
`zuno_postgresql_backup_s3_path`, the same variable the operand uses, so probe
and operand cannot drift again. Default `/pgbackrest/repo2` — what PGO already
writes. **Live verification still owed**: the probe runs only from `install.yml`
(gated on the PostgresCluster being absent, so inert on `demo222`) and from
`restore.yml` (which would then actually restore), so it has to be exercised
standalone rather than through either entry point.

### P0-b — `make d3 backup postgresql` cannot trigger a backup

The chart has no `manual:` block (`grep manual` on the template returns nothing),
and PGO 5.x needs `manual.repoName` + `manual.options` for the
`pgbackrest-backup` annotation to do anything. `backup.yml` sets the annotation
and then polls `status.pgbackrest.scheduledBackups`, never `manualBackup`. It
patches an inert annotation and waits for a scheduled run.

This matters here because the single most important step of the cutover is
"take a new full backup on the new path immediately".

**Fixed 2026-09-04.** The chart now declares `spec.backups.pgbackrest.manual`
(`repoName` resolving to `repo2` when the S3 repo is enabled, else `repo1`;
`--type=full`), and `backup.yml` waits on `status.pgbackrest.manualBackup`
instead. The wait is now an identity check — PGO copies the annotation value
verbatim into `manualBackup.id`, so the task waits for *the run it started*
rather than comparing timestamps that cannot tell one backup from another. It
also checks `succeeded > 0` and not only `finished`, which `oc explain` states
does not indicate success.

## Mapping

Operator decisions taken 2026-09-04: weights are **copied now, `storageUri`
flips later, one model at a time**; pgBackRest history **is** copied; traces are
not.

| # | Content | Today | Target | Size | Moves? |
|---|---|---|---|---|---|
| 1 | Model weights | `zuno-demo-rag-corpus/models/` | `zuno-demo-sources/models/` | **164.6 GB / 226** | **Copy**, cutover deferred |
| 2 | lmeval tokenizer source | as #1 | follows #1 | — | with #1 — *ADR correction* |
| 3 | Authoritative SXA dump | `zuno-demo-sxa-corpus/sxa.{schema,data}.sql` | `zuno-demo-sources/sxa-dump/` | 136 MB / 2 | **Yes** |
| 4 | Stale SXA duplicate | `zuno-demo-rag-corpus/sxa_data/` | — | 136 MB / 5 | **No** — orphan, no consumer |
| 5 | Training corpora | `zuno-corpus/qwen-wesh-training-corpus{,-v0,-v1}.tgz` | `zuno-demo-sources/training-corpus/` | ~210 KB / 3 | **Yes** (cross-region) |
| 6 | RAG ingestion outputs | `zuno-demo-rag-corpus/{raw,normalized,manifests,failed}*` | `zuno-demo222-data/` | many small | **No — re-ingest** (ADR cl.1) |
| 7 | KFP run artifacts, rag | `zuno-demo-rag-corpus/rag-corpus-ingestion*/` | `zuno-demo222-data/` | — | **No** — ephemeral |
| 8 | mlops pipeline objects | `zuno-corpus/mlops/*` | `zuno-demo222-mlops/mlops/` | ⊂ 674 MB | **Yes** — `train_manifest.json` points at it |
| 9 | mlops KFP artifacts | `zuno-corpus/mlops-comage/` | `zuno-demo222-mlops/` | ⊂ 674 MB | Optional |
| 10 | MLflow artifacts | `zuno-corpus/mlflow-artifacts` | `zuno-demo222-mlops/mlflow-artifacts` | **does not exist** | N/A |
| 11 | pgBackRest repo2 | `zuno-data-pgbackups/pgbackrest/repo2/` | `zuno-demo222-backups/postgresql/` | 3 fulls | **Yes** — own sequence |
| 12 | MariaDB PhysicalBackup | `zuno-data-pgbackups/zuno-mariadb/` | `zuno-demo222-backups/mariadb/` | ~35 MB | **Yes** |
| 13 | AAP Hub content | `zuno-aap-hub` | `zuno-demo222-aap-hub` | **empty** | N/A |
| 14 | RHOAI traces | `zuno-demo-rhoai-traces/` | `zuno-demo222-traces` | — | **No** — history becomes unqueryable |

## Commands

### The IAM prerequisite, stated first

A server-side S3 copy runs under **one principal**, which needs
`s3:GetObject`+`s3:ListBucket` on the source **and**
`s3:PutObject`+`s3:AbortMultipartUpload`+`s3:ListBucket` on the destination.

**Correction, 2026-09-04.** This brief previously said none of the app users
could do that because each is bucket-scoped. That is false, and the truth
matters more than the original claim. An IAM audit of account `791728029433`
found the six credential families in `confidential.yml` are **three IAM users**,
and **all three can read and write every `zuno*` bucket**:

| Credential family in `confidential.yml` | IAM user | Grant |
|---|---|---|
| `zuno_rag_s3_*` | `zuno-demo-rag-corpus` | **`AmazonS3FullAccess`** + `AmazonS3FilesFullAccess` — account-wide |
| `zuno_postgresql_backup_s3_*`, `zuno_mariadb_backup_s3_*` | `zuno-demo` | **`AmazonS3FullAccess`** — account-wide |
| `zuno_sxa_corpus_s3_*`, `zuno_aap_hub_s3_*`, `zuno_rhoai_traces_s3_*` | `zuno-sxa-corpus-s3` | inline `sxa-corpus-bucket-only`, which despite its name allows `Get/Put/DeleteObject` on `arn:aws:s3:::zuno*/*` and `ListBucket` on `arn:aws:s3:::zuno*` |

Three consequences. The migration **can** technically run under an existing
credential — but it should not, and a dedicated identity is now a least-privilege
choice rather than a capability requirement. WP-079's finding, that
`zuno-sxa-corpus-s3` was reused for AAP Hub and RHOAI traces, is **still the live
state**: only the missing grant was patched, the reuse was never undone. And
most importantly, because the policies are keyed on the prefix `zuno*`,
**creating the new buckets grants all three existing users full access to them
automatically** — provisioning is not the isolation step. ADR-0546 clause 3 is
therefore not a refinement but the remediation of a real over-grant, and its
effect is measurable before and after.

Create a dedicated, time-boxed `zuno-s3-migration-wp131` whose key lives only in
the operator's shell (`AWS_PROFILE=zuno-migration`), never in `confidential.yml`
and never in Vault, deleted when the migration ends. Not the account admin
credentials — `confidential.example.yml` states that rule already.

`s3:ListBucket` must be granted on the bucket ARN **separately** from
`GetObject`/`PutObject` on `/*` — that is the WP-079 bug — and the new
per-bucket policies must name buckets **explicitly**, never `zuno*`, or they
recreate exactly what they are meant to fix.

If any source bucket uses SSE-KMS, the same principal also needs `kms:Decrypt`
on the source key and `kms:GenerateDataKey` on the destination key, or every
copy fails `AccessDenied` on an object it can plainly list.

The migration policy must include the **tagging** actions, and this was learned
the hard way on 2026-09-04: a first attempt granted only
`GetObject`/`ListBucket` on the sources and every large object failed with
`AccessDenied ... s3:GetObjectTagging`. The failure is size-dependent and
therefore easy to misread — below the multipart threshold the CLI issues a
single `CopyObject` with `x-amz-tagging-directive: COPY` and never reads tags,
while above it the multipart copy must read them explicitly. 126 small objects
copied fine and all 100 `.safetensors` failed. Grant `s3:GetObjectTagging` and
`s3:GetObjectVersionTagging` on the sources and `s3:PutObjectTagging` on the
destinations. (`--copy-props metadata-directive` avoids the tag calls entirely
and is the alternative if the grant is unwanted; it drops object tags, which is
acceptable only if there are none to keep.)

Cost: #1 is intra-region, so 164.6 GB moves with no transfer charge. #5 and #8
are `us-east-1` → `eu-west-2`, ~674 MB of egress, negligible.

### Check the existing buckets first

Per bucket: `get-bucket-versioning`, `get-bucket-encryption` (SSE-KMS drives the
KMS grants), `get-public-access-block`, `get-bucket-ownership-controls`,
`get-bucket-policy`, **`get-bucket-lifecycle-configuration`** (an existing expiry
rule would make the "history" shorter than `pgbackrest info` claims), and
`get-bucket-tagging`.

### Create

```bash
for B in zuno-demo-sources zuno-demo222-data zuno-demo222-mlops \
         zuno-demo222-backups zuno-demo222-traces zuno-demo222-aap-hub; do
  aws s3api create-bucket --bucket "$B" --region eu-west-2 \
    --create-bucket-configuration LocationConstraint=eu-west-2
  aws s3api put-public-access-block --bucket "$B" --region eu-west-2 \
    --public-access-block-configuration \
      BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  aws s3api put-bucket-ownership-controls --bucket "$B" --region eu-west-2 \
    --ownership-controls 'Rules=[{ObjectOwnership=BucketOwnerEnforced}]'
  aws s3api put-bucket-encryption --bucket "$B" --region eu-west-2 \
    --server-side-encryption-configuration \
      '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":true}]}'
done
```

**Versioning on `zuno-demo-sources` only**, with noncurrent versions expiring at
30 days: a mistake there is a fleet-wide serving outage and an overwritten
checkpoint is otherwise unrecoverable. **Never on `zuno-demo222-backups`** —
pgBackRest `expire` and MariaDB's `maxRetention` delete objects by design, so
versioning would turn every expiry into a retained noncurrent version and the
bucket would grow without bound. Protect deletes there with a `Deny
s3:DeleteObject` policy scoped to everything except the two backup users.

### CLI tuning, once

226 objects averaging ~730 MB, several above the 5 GB `CopyObject` ceiling and
therefore forced into multipart copy:

```bash
aws configure set --profile zuno-migration s3.max_concurrent_requests 20
aws configure set --profile zuno-migration s3.multipart_chunksize 512MB
```

### The copies

```bash
export AWS_PROFILE=zuno-migration

# 1. Weights - 164.6 GB, intra-region (the long one). `sync`, not
# `cp --recursive`: sync skips what is already there, so a re-run after a
# failure resumes instead of recopying 164 GB.
aws s3 sync s3://zuno-demo-rag-corpus/models/ s3://zuno-demo-sources/models/ \
  --source-region eu-west-2 --region eu-west-2 --only-show-errors

# 3. Authoritative SXA dump (NOT the 2026-08-21 sxa_data/ copy)
aws s3 cp s3://zuno-demo-sxa-corpus/sxa.schema.sql s3://zuno-demo-sources/sxa-dump/sxa.schema.sql \
  --source-region eu-west-2 --region eu-west-2
aws s3 cp s3://zuno-demo-sxa-corpus/sxa.data.sql   s3://zuno-demo-sources/sxa-dump/sxa.data.sql \
  --source-region eu-west-2 --region eu-west-2

# 5. Training corpora - CROSS-REGION us-east-1 -> eu-west-2
for T in qwen-wesh-training-corpus.tgz qwen-wesh-training-corpus-v0.tgz qwen-wesh-training-corpus-v1.tgz; do
  aws s3 cp "s3://zuno-corpus/$T" "s3://zuno-demo-sources/training-corpus/$T" \
    --source-region us-east-1 --region eu-west-2
done

# 8. mlops pipeline objects - CROSS-REGION
aws s3 cp --recursive s3://zuno-corpus/mlops/ s3://zuno-demo222-mlops/mlops/ \
  --source-region us-east-1 --region eu-west-2 --only-show-errors

# 12. MariaDB history - intra-region, prefix rename
aws s3 cp --recursive s3://zuno-data-pgbackups/zuno-mariadb/ s3://zuno-demo222-backups/mariadb/ \
  --source-region eu-west-2 --region eu-west-2 --only-show-errors
```

**Do not run** for #4, #6, #7, #13, #14. #11 has its own sequence below.

### Verify a copy

```bash
aws s3 ls --recursive --summarize s3://zuno-demo-rag-corpus/models/ | tail -3
aws s3 ls --recursive --summarize s3://zuno-demo-sources/models/    | tail -3   # counts and bytes must match
aws s3 sync --dryrun s3://zuno-demo-rag-corpus/models/ s3://zuno-demo-sources/models/ \
  --source-region eu-west-2 --region eu-west-2                                  # must print nothing
```

**Do not compare ETags.** A server-side copy recomposes a multipart object and
its ETag is a function of part boundaries, so a mismatch there is expected and
means nothing. For pgBackRest the real integrity proof is `pgbackrest verify`,
which checksums every file against the manifest.

## The pgBackRest sequence

Two properties drive it. WAL segments and completed backup sets are **immutable
and uniquely named**, so copying them twice is free and idempotent. But
`archive.info` and `backup.info` are **mutated in place** — they are the only
files where "sync again later" destroys information.

**Volume, measured 2026-09-04 — repo2 is 105.4 GB across 52,469 objects**, not
the handful of small backup sets the mapping table implies. The three backup sets
are only 3.2 GB (17 MB / 387 MB / 2.9 GB); **102.2 GB across 32,104 objects is
archived WAL** accumulated since 2026-08-16 for a 7.7 GB database, because repo2
has no retention rule at all — only `repo1-retention-full` exists. Decision
(operator, 2026-09-04): **copy it all as-is**, and set repo2 retention only after
the restore drill passes on the new bucket, so the old bucket stays an intact
fallback and no restore point is destroyed to save transfer.

Do **not** quiesce PostgreSQL: it buys nothing, the WAL archiving has already
happened.

```
P0   LIVE-VERIFY P0-a - it has never actually run. check_s3_backup.yml is only
     called when the PostgresCluster is ABSENT (install.yml's auto-restore
     gate), so on a live cluster the fixed probe is inert. precheck.yml now
     carries the same probe, so:
       make d3 check postgresql
     must report the three real backup sets (20260816-030006F, 20260823-131414F,
     20260830-030007F) and say the bucket agrees with the operator.
     COUNTER-TEST, mandatory - a probe that reports three either way is not
     reading the path at all:
       make d3 check postgresql EXTRA_VARS='-e zuno_postgresql_backup_s3_path=/wrong'
     must report zero. Keep `pgbackrest info --repo=2 --output=json` as the
     baseline for P10.
P1   DONE 2026-09-04 (repo work): the `path` parameter is wired through the
     chart's global block, install.yml and BOTH restore.yml blocks, defaulting
     to /pgbackrest/repo2. Confirmed live: the PostgresCluster carries
     repo2-path: /pgbackrest/repo2 and manual: {repoName: repo2,
     options: [--type=full]}, both applied by selfHeal.
P2   BACKUP TEST - the first on-demand backup this cluster has ever completed
     (status.pgbackrest.manualBackup is null, so any non-null result is caused
     by this run, which is what makes it a proof):
       make d3 backup postgresql
     Requires all three: manualBackup.id equals the generated id, finished:
     true, succeeded > 0 - AND a new F set under
     s3://zuno-data-pgbackups/pgbackrest/repo2/backup/db/.
P3   RESTORE DRILL from the CURRENT repo2, non-destructively. repo2 has NEVER
     been restored from: the 2026-08-18 and 2026-08-25 drills both used repo1,
     the local PVC. A throwaway PostgresCluster (zuno-postgresql-drill, in
     zuno-data) bootstrapped straight from S3 via spec.dataSource.pgbackrest -
     the "cloud" form, confirmed present in the installed CRD - never touches
     zuno-postgresql. Sizing: the whole database is 7.7 GB (rag-sxa-legacy
     5.2 GB, rag-tech 2.2 GB), so ~30Gi pgdata and a minimal repo1 suffice.
     Acceptance is a REAL row count on rag-sxa-legacy compared against the live
     cluster, not "the pods are Ready". Then delete the cluster and its PVCs.
     Nothing touches a bucket until this is green.
P4   Pick a window OUTSIDE Sunday 02:00-04:00 (repo1 full 0 2 * * 0, repo1 diff
     0 2 * * 1-6, repo2 full 0 3 * * 0). A backup split across two paths is
     unrecoverable as a unit.
P5   Bulk copy, 105.4 GB / 52,469 objects, intra-region, server-side:
       aws s3 sync s3://zuno-data-pgbackups/pgbackrest/repo2/ \
                   s3://zuno-demo222-backups/postgresql/
     sync, not cp --recursive, so a resume after any interruption is
     incremental over 52k objects rather than a restart.
P6   Delta immediately before the flip: same command, NEVER --delete. This pass
     carries archive.info and backup.info, which is what makes the new path a
     VALID stanza instead of an empty one. Confirm both files arrived.
P7   FLIP: zuno_postgresql_backup_s3_{path,bucket} in confidential.yml, then
     make d0 install postgresql. stanza-create becomes a no-op and adopts the
     history. Also re-run make d0 install vault so zuno/postgresql/backup-s3
     stays consistent (its kv put rewrites all five keys together) - no effect
     on demo222, required for demo333.
P8   Close the flip-window WAL hole - ARCHIVE ONLY, info files EXCLUDED:
       aws s3 sync .../repo2/archive/ .../postgresql/archive/ \
         --exclude "*/archive.info" --exclude "*/archive.info.copy"
     Do NOT re-sync backup/ after the flip.
P9   select pg_switch_wal(); confirm the new bucket gains a segment and the old
     one does not.
P10  pgbackrest verify, then info; diff against the P0 baseline.
P11  New full backup on the new path: make d3 backup postgresql.
P12  SECOND RESTORE DRILL, from the NEW bucket, same throwaway-cluster
     mechanism as P3. This is the acceptance criterion for the cutover.
P13  Only now: repo2 retention (repo2-retention-full and the archive retention
     that follows it). Expiring 102 GB of WAL is safe here because it happens
     in the NEW bucket while the old one is still intact; set in P7 it would
     have deleted the history just migrated. Then the chart default flip.
P14  Old bucket read-only (explicit Deny policy) for a full cycle, then delete.
```

### What is lost if the order is wrong

| Mistake | Consequence | Detectable? |
|---|---|---|
| Skip P0 | Any rebuild bootstraps an **empty database** while announcing a fresh environment. Total, silent | No — the probe reports success |
| Skip P0's counter-test | A probe that ignores the path reports three backups whether or not it works | No — that is the whole point |
| Skip P3 | The migration is built on a repo nobody has ever restored from | Only during a real incident |
| Flip before P6 | `stanza-create` builds an empty stanza; no off-cluster restore point | Yes, `info` is empty |
| Skip P8 | **WAL hole.** Backups look perfect; PITR silently cannot roll forward across the window. You find out during an incident | **No** |
| P8 without the `.info` exclusions | Overwrites live info files with pre-flip copies | Only via `verify` |
| Retention set at P7 | The first `expire` **deletes the history just migrated** | Too late |
| A broken repo2 left in place | `archive-push` fails for all repos, WAL is not released, the WAL volume fills and **PostgreSQL halts** | Yes, loudly |

That last row is why P7 is a single reversible variable pair: rollback is two
lines in `confidential.yml` plus one `make d0 install postgresql`.

**repo2 has no retention at all today** — only `repo1-retention-full` exists — so
fulls have accumulated since 2026-08-16 and `archive/` is never pruned, which is
where the 102.2 GB comes from. Fix it at **P13**, never at P7, and only once a
drill has passed against the new bucket.

## Rewiring, in ADR-0547 clause 4's two-step order

Pin the **current** value at the Application level → prove the render
byte-identical **with the toggle on** → apply live → confirm ArgoCD synced a
revision containing the commit → only then flip the chart default. The bucket
cutover itself happens by changing the **variable** between the last two steps,
which is where the rollback lever lives.

**Two repo-wide prerequisites.** `mlflow`, `mlops` and `rag_ingestion` **do not
load `confidential.yml`** (verified). Add the `stat` + `include_vars` pair in the
same commit that gives them their first variable, or it is ADR-0517 B13 again:
the variable stays undefined and `| default(<chart>)` wins silently.
`check_confidential_var_loaders` now catches it. And a
`gitops_app_extra_helm_values` **dict replaces** `spec.source.helm.values`
wholesale, so the new dicts must carry the keys already declared in their
manifests — `mlflowConfig.enabled` for mlflow, `acceptanceGate.keycloakUrl` and
`.frontendUrl` for mlops. The case the linter **cannot** see is
`backups.s3.path` in **both** blocks of `postgresql/tasks/restore.yml`, because
`path` is not declared in the Application manifest.

| Component | Cutover | Live risk |
|---|---|---|
| **mlflow** — **DONE 2026-09-04** | `zuno-corpus`/us-east-1 → `zuno-demo222-mlops`/eu-west-2. Both workspace Secrets and the MLflow CR moved together | Low, as expected — nothing had ever been written |
| **mariadb** — **DONE 2026-09-04** | Bucket + the newly parameterized prefix. Needed a **delete-and-recreate**: spec.storage is immutable, see below | Low, but not the shape expected |
| **aap** — **DONE 2026-09-04** | `zuno_aap_hub_s3_bucket_name`; no chart change, and nothing to flip in git either — the example file carries placeholders | Low, both buckets empty |
| **mlops** | `s3.bucket`, `s3.region`, `styleCorpusS3Uri`. Not yet `mergedModel.s3Uri` or `trainjob.baseModel` — those name the *models* bucket | Medium — in-flight runs break |
| **rag-ingestion** | `s3.bucket` → `-data`; `sxaDump` → `zuno-demo-sources` with `sxa-dump/…` keys | **High** — the corpus vanishes from the app's view until re-ingestion; the DSPA reconciles and kills in-flight runs |
| **openshift-ai** | `zuno_rhoai_traces_s3_bucket_name`; no chart change | Medium — **historical traces become unqueryable** |
| **postgresql** | Bucket + `path` | **Highest** — see above |
| **models** | **Copy only.** Land the per-model cutover mechanism, inert | None if the defaults are right |

**The models chart needs a mechanism or "one model at a time" is impossible**:
all five `storageUri` values and the prefetch Job derive from the single
`modelsS3.bucket`, so changing `zuno_models_s3_bucket` moves **all five at
once**. Land a `sourcesS3` block and a per-model `s3Source` key defaulting to
`models` — the render stays byte-identical, which is a real inertia proof rather
than an empty-vs-empty one. A later flip is then `weshModel.s3Source: sources`,
one model, reversible.

**Code literals**: `components/mlops/tooling/backfill_mlflow.py`'s
`default="zuno-corpus"` is the only functional fallback — remove it so it fails
loudly; `components/mlops/tests/test_trainjob.py`'s fixture becomes a neutral
value; `evaluations/register_conformance.py`'s mention is docstring provenance
that stays true — **leave it**.

### AAP Hub: the cutover is three hops, and only the last one counts

`zuno_aap_hub_s3_bucket_name` → Vault `zuno/aap/hub-s3` → ExternalSecret
`aap-hub-s3-credentials` → **the operator-generated `aap-hub-server` Secret's
settings.py** → a rolling restart of api/content/worker. Measured 2026-09-04:
the credentials Secret updated within seconds of `make d0 install vault`, and
`settings.py` still named the old bucket for **six more minutes** before the AAP
operator regenerated it and rolled the pods. Reading the credentials Secret is
therefore not a verification — it is the hop that moves first and proves least.

`make d0 install vault` does overwrite this path: the "seed only if missing"
guard (`vault_seed_if_missing.yml`) covers only the self-generatable secrets,
not operator-supplied ones like `zuno/aap/hub-s3`, which use a plain `kv put`.

Proof used, and the shape worth reusing: a write through the Hub's OWN storage
backend rather than an inference from config.

```bash
oc exec -n zuno-aap deploy/aap-hub-api -- bash -lc 'pulpcore-manager shell -c "
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings
print(settings.AWS_STORAGE_BUCKET_NAME)
n = default_storage.save(\"wp131-probe.txt\", ContentFile(b\"wp131\"))
print(default_storage.exists(n)); default_storage.delete(n)"'
```

It exercises credentials, bucket, region and the boto3 path the Hub actually
uses, writes one tiny object and removes it. Absence of errors in the pod logs
proves nothing here: the Hub had never written to either bucket, so a broken
configuration and a correct idle one look identical.

### PhysicalBackup's spec.storage is immutable — the mariadb cutover is a recreate

Found live 2026-09-04, and it is the one place in this WP where the ADR-0547
two-step order is not enough on its own. Changing `bucket` or `prefix` makes the
validating webhook `vphysicalbackup-v1alpha1.kb.io` reject the patch:

```
PhysicalBackup.k8s.mariadb.com "mariadb-backup" is invalid:
spec.storage: Invalid value: {...}: 'spec.storage' field is immutable
```

**ArgoCD does not turn that into a recreate.** It retries the same patch, and
the Application sits `SyncFailed` on this single resource — everything else
Synced, MariaDB Ready — with no time limit. Nothing degrades, so nothing alerts;
it simply never converges.

The fix is `oc delete physicalbackup mariadb-backup -n zuno-data` and letting
`automated`+`selfHeal` recreate it. Safe, and checked before doing it: the CR
carries no finalizer and no ownerReferences, and the CRD applies `maxRetention`
from the backup Job rather than on deletion, so no S3 object is touched. The
recreated CR runs a backup **immediately** instead of waiting for its next cron
slot, which is what proved the cutover: `physicalbackup-20260904131912.xb.gz`,
4 MB, landed in `zuno-demo222-backups/mariadb/` within seconds, condition
`Complete/Success`. The stale `Failed` condition described below went with it.

Same question to ask of every other operand in this WP before flipping it: is
the field being changed immutable? PGO's `spec.backups` is not — `repo2-path`
and the `manual` block were both patched in place on the live PostgresCluster.

### The MariaDB backup-health trap

`oc get physicalbackup -n zuno-data` shows `mariadb-backup` as **`STATUS Failed`**.
It is not failing. The `Complete` condition's `lastTransitionTime` is frozen at
2026-09-02T21:52:43Z — the first run, which did fail — and the operator never
cleared it, while every scheduled run since has Completed and landed its object
in S3 (five of them, through 2026-09-04T07:24). **That column is not a health
signal.** When verifying the mariadb cutover, read `status.lastScheduleTime`, the
`mariadb-backup-*` pod phases, and the bucket itself — a green flip judged from
that column would be judged from a value that has not moved in two days.

## Vault paths

Six new paths per ADR-0546 clause 3: `zuno/sources/s3` and
`zuno/demo222/{data,mlops,backups,traces,aap-hub}-s3`, with **two** users for
`backups` (prefixes `postgresql/*` and `mariadb/*`), which that clause provides
for.

**One narrowing to record.** `components/mlops/src/mlops.py` builds its clients
from a **single** credential, and after the split mlops must read *and write*
`zuno-demo-sources/models/` — ADR-0546 clause 1 promotes fine-tuned checkpoints
directly there — **and** `zuno-demo222-mlops/`. Clause 3 says one user per
bucket; ADR-0547 clause 2 says one path and one identity **per consumer**. Follow
ADR-0547 and record the narrowing; the alternative is a real change to
`ArtifactStore` to carry two credentials.

Worth normalizing in passing: properties are `access_key`/`secret_key`
(snake_case) for postgresql and `accessKeyId`/`secretAccessKey` (camelCase)
everywhere else. And **no S3 path is in the vault role's expected-paths loop**,
so a mis-seeded path fails silently.

For AAP Hub and RHOAI traces, `make d0 install vault` after editing
`confidential.yml` **is** the cutover — `bucketName` in Vault is what those two
ExternalSecrets read.

## Recommended order

1. **P0-a** — independent, urgent, ship it alone.
2. **P0-b** — needed before P10.
3. Buckets + migration identity + copies #1, #3, #5, #8, #12.
4. **mlflow** — the cheapest rehearsal.
5. **mariadb**, **aap**.
6. **mlops**, **openshift-ai**.
7. **rag-ingestion** — schedule the re-ingestion immediately after.
8. **postgresql** — the full P1→P13 sequence.
9. `zuno_s3_bucket_owner_cluster` stays `demo222`; WP-130's probe P6 keeps
   protecting a future `demo333`.
10. Old buckets read-only for a full cycle, then deleted.

## Risks and known unknowns

- P0-a is a live data-loss trap and is not hypothetical: three full backups exist
  that the platform believes are absent.
- Backup buckets are the sharp edge — a pgBackRest stanza that loses its history
  is not recoverable by re-running anything.
- Model weights move to a bucket every cluster reads. A mistake there is a
  fleet-wide serving outage, not a one-cluster one — hence versioning on
  `zuno-demo-sources` alone.
- The `storageUri` cutover is deliberately out of this WP: re-pulling 164.6 GB
  onto GPU nodes that already have an open DiskPressure problem is its own
  operation, done one model at a time.
- None of this is exercised against a second cluster until `demo333` exists.
