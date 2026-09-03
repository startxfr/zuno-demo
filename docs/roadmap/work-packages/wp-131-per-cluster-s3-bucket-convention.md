# WP-131: Execute ADR-0546's cross-cluster source bucket and per-cluster S3 convention

- **State:** Not started
- **ADRs:** [ADR-0546](../../adr/0546-introduce-a-cross-cluster-source-bucket-and-per-cluster-s3-bucket-convention.md)
  (this WP satisfies its acceptance criterion 2 — "a follow-up work package exists"),
  [ADR-0517](../../adr/0517-redeploy-the-full-platform-from-scratch-on-a-new-demo333-cluster.md) (B12),
  [ADR-0547](../../adr/0547-parameterize-every-cluster-specific-value-in-ansible.md) (clause 2's Vault surface)
- **Depends on:** ADR-0546 moving to `Accepted` (a human decision, its own acceptance
  criterion 1), and manual AWS bucket provisioning — there is no AWS IaC in this
  repository
- **Related:** [WP-130](wp-130-fresh-cluster-readiness-gate.md) (probe P6 detects B12
  until this lands), [WP-118](wp-118-demo333-portability-blockers.md) (closed the one S3
  gap it could — B8's undocumented MariaDB variables — and explicitly left bucket
  sharing-vs-duplication undecided), [WP-079](wp-079-rhoai-monitoring-traces.md) (the
  live IAM-scoping bug this WP's per-consumer identities prevent)

## Goal

Give each cluster its own S3 buckets, and put the data that seeds *any* cluster in one
shared source bucket. Until that exists, a second cluster installed from this repository
writes its RAG ingestion outputs, pgBackRest and MariaDB backups, RHOAI traces and MLflow
artifacts into the first cluster's buckets.

That is ADR-0517's B12, and it is the only blocker on that list which damages the
**existing** cluster rather than the new one. It is a direct violation of ADR-0517's own
"`demo222` is left untouched — this is a parallel proof, not a migration" criterion, so
this WP gates the `demo333` run.

## Scope

ADR-0546 decided the shape; this WP executes it. Nothing here changes what was decided.

1. **Provision** `zuno-demo-sources` (cross-cluster inputs: `models/<servedModelName>/`,
   `sxa-dump/`, `training-corpus/`) and the `zuno-demo222-*` set (`-data`, `-mlops`,
   `-backups`, `-traces`, `-aap-hub`), all in `eu-west-2` per ADR-0546 clause 4.
   Manual — there is no AWS IaC here.
2. **Migrate** the data per ADR-0546's old→new mapping table. An already-ingested RAG
   corpus is explicitly *not* migrated: ADR-0546 clause 1 says each cluster re-runs its
   own ingestion against the raw sources, and re-ingestion is the already-optimized path
   (ADR-0519/ADR-0520).
3. **Credentials** — one IAM user and one Vault path per bucket (`sources/s3`,
   `demo222/data-s3`, `demo222/mlops-s3`, `demo222/backups-s3`, `demo222/traces-s3`,
   `demo222/aap-hub-s3`), per ADR-0546 clause 3 and ADR-0547 clause 2. The shared
   `demo222-backups` bucket keeps two scoped IAM users, one per DB engine, each restricted
   to its own prefix. This is the concrete closure of the gap WP-079 hit live, where the
   `zuno-sxa-corpus-s3` user was reused for AAP Hub and RHOAI traces without the right
   `s3:ListBucket` grant.
4. **Rewire** `ansible/confidential.yml` and `confidential.example.yml`, the `vault`
   role's seed tasks, and the affected charts' `values.yaml`/ExternalSecret templates:
   `models`, `rag-ingestion`, `mlflow`, `mlops`, `mariadb`, `postgresql`, `aap`,
   `openshift-ai`. Bucket names become Ansible parameters keyed on `zuno_cluster_name`,
   per ADR-0547 clause 1 — not new literals under new names.
5. **Decommission** the old buckets once every consumer is verified on the new ones.

Two anomalies ADR-0546 records get fixed in passing: `zuno-corpus` is undocumented in
`confidential.example.yml` and lives in `us-east-1`, forcing mlops to build two separate
boto3 clients.

## Delivery constraint

ADR-0547 clause 4 applies in full, and it bites harder here than anywhere else. Every
`gitops/apps/*/application-*.yaml` renders from git `main` with `selfHeal: true`, so
flipping a chart's bucket default is a live change on `demo222`. Each bucket moves in two
steps — pin the current bucket name at the Application level and prove the render
byte-identical, then flip the chart default — and the *data* must be in the new bucket
before the parameter points at it.

`postgresql`'s `restore.yml` needs particular care: both of its blocks replace
`spec.source.helm.values` wholesale, so omitting the new values there would silently
revert the install-time value. WP-118 step 3a hit exactly this and had to wire both
blocks.

## Verification (operator steps — ask before running)

- Every consumer reads and writes its new bucket: a RAG ingestion run, a pgBackRest
  backup, a MariaDB PhysicalBackup, an MLflow artifact write, an RHOAI trace, an AAP Hub
  upload.
- Each IAM identity can reach **only** its own bucket and prefix — the WP-079 failure
  mode is a missing `s3:ListBucket`, which a write-only smoke test does not catch.
- `make d0 check` reports no readiness findings, and WP-130's probe P6 goes silent.
- The old buckets are read-only for a full backup cycle before deletion.

## Risks and known unknowns

- Blocked on a human decision (ADR-0546 → `Accepted`) and on manual AWS work. Neither is
  a repository change, and neither can be worked around from here.
- Backup buckets are the sharp edge: a pgBackRest stanza that loses its history is not
  recoverable by re-running anything.
- Model weights move to `zuno-demo-sources`, which every cluster reads. A mistake there
  is a fleet-wide serving outage, not a one-cluster one.
