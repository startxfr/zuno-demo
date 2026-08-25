# WP-077: Automate aap/aap-eda Postgres cleanup on `aap` uninstall/install

- **State:** Code committed 2026-08-25, corrected after first live run
  exposed a wrong assumption (see "Correction" below), pending a full
  clean live run.
- **Depends on:** WP-072 (`aap` chart/role), WP-075 ([[wp075-aap-hub-s3-live-verified]]).
- **Related:** [[aap-uninstall-reinstall-encryption-key-trap]]

## Correction (2026-08-25, same day, first live run)

The original design assumed Crunchy PGO's continuous reconcile of
`PostgresCluster.spec.users[]` would recreate a dropped database/role on
its own. **Wrong** - confirmed live via the PGO operator's own logs
(`openshift-operators/pgo`), which error-looped every ~2 seconds on
`reconcilePostgresUsersInPostgreSQL`: `psql:<stdin>:47: ERROR: database
"aap" does not exist` / `command terminated with exit code 3`, forever,
never creating it - and this also blocked PGO's entire cluster reconcile,
not just the aap-specific part. PGO's ongoing reconcile only manages
roles/grants *inside* databases it assumes already exist; database
creation apparently only happens at initial cluster bootstrap, not as
self-healing recovery for a database that later disappears.

Fixed by having `ansible/roles/aap/tasks/install.yml`'s recovery block
explicitly `CREATE ROLE`/`CREATE DATABASE` itself (using the
still-present PGO-managed SCRAM verifier from
`zuno-postgresql-pguser-<role>` for the password, so existing credential
consumers keep working) instead of waiting for PGO to do it. Also
deliberately standardized both databases on the chart's documented
"owned by postgres, role granted DB-level access" model (matching
`aap-eda`'s actual structure) rather than perpetuating `aap`'s
unexplained direct-ownership-by-`aapgateway` anomaly from the original
WP-072 bootstrap - schema-level access still comes from the
already-planned force-sync-postgresql step (unchanged, still correct).

## Why

`make d1 uninstall aap` + `make d1 install aap` hit the encryption-key trap
twice live (2026-08-25): Gateway's and EDA's Fernet secrets are owned by
the umbrella CR and get garbage-collected + regenerated on every
uninstall/reinstall, while their external Postgres databases (`aap`,
`aap-eda`) persist with data encrypted under the now-gone key, crashing
migrations with `cryptography.fernet.InvalidToken`. Both had to be fixed
by hand (`DROP DATABASE ... WITH (FORCE)`, then recreate + schema
grants). This WP automates that recovery.

## What changed

- `ansible/tasks/force_argocd_sync.yml` (new): factors the
  `spec.operation.sync` patch + wait-for-completion logic out of
  `apply_gitops_app.yml` into a standalone, reusable task — safe to call
  against an Application owned by a different role since it never
  touches `spec.source`.
- `ansible/roles/aap/tasks/uninstall.yml`: drops the `aap`/`aap-eda`
  databases (`WITH (FORCE)`, PG13+) and their dedicated roles
  (`aapgateway`/`aapeda`), `IF EXISTS` throughout for idempotency.
- `ansible/roles/aap/tasks/install.yml`: a cheap precheck skips the whole
  recovery path on the normal install case (databases already present).
  When either is missing: reads the `verifier` field from
  `zuno-postgresql-pguser-aapgateway`/`-aapeda` (no_log'd), explicitly
  `DROP ROLE IF EXISTS`/`CREATE ROLE ... PASSWORD '<verifier>'`,
  `DROP DATABASE IF EXISTS ... WITH (FORCE)`/`CREATE DATABASE` +
  `GRANT CREATE, TEMPORARY, CONNECT` for both, **then** force-syncs
  `zuno-postgresql-d1` so the `<cluster>-schema-grants` Sync-hook Job
  reruns and applies `GRANT CREATE, USAGE ON SCHEMA public` (PG15+
  doesn't imply this from the database-level grant above). The
  create-before-sync ordering matters: the schema-grants script covers
  all 16 dedicated databases in one `ON_ERROR_STOP=1` psql invocation,
  and `aap`/`aap-eda` sit before `aap-controller`/`aap-hub` in that list
  — syncing before they exist would abort the script and leave sibling
  databases' grants unapplied too.

## Live incident during first run (2026-08-25, fixed same session)

`make d1 reinstall aap` got stuck retrying "wait for PGO to (re)create
the aap and aap-eda databases" for the original (pre-correction) code -
see "Correction" above. Manually recreated both databases/roles live to
unblock PGO's error-looping cluster reconcile immediately (matching
what the corrected code now does automatically), then fixed the ansible
task itself before the next attempt.

## Verification checklist

- `make d1 uninstall aap` then `\l`/`\du` via psql confirms `aap`/
  `aap-eda` and `aapgateway`/`aapeda` are gone.
- `make d1 install aap` completes with no `InvalidToken`, "permission
  denied for schema public", or PGO reconcile errors in the operator
  logs (`openshift-operators/pgo`) - no manual intervention.
- `zuno-postgresql-d1`'s `status.operationState` shows a sync triggered
  during the install run.
- `aap-controller`/`aap-hub` schema grants (`\dn+ public`) still intact
  afterward - confirms the ordering fix worked.
