# WP-077: Automate aap/aap-eda Postgres cleanup on `aap` uninstall/install

- **State:** Code committed 2026-08-25, pending live rollout/verification.
- **Depends on:** WP-072 (`aap` chart/role), WP-075 ([[wp075-aap-hub-s3-live-verified]]).
- **Related:** [[aap-uninstall-reinstall-encryption-key-trap]]

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
  When either is missing, waits (up to 15 min) for Crunchy PGO's own
  continuous reconcile of `PostgresCluster.spec.users[]` to recreate
  both databases, **then** force-syncs `zuno-postgresql-d1` so the
  `<cluster>-schema-grants` Sync-hook Job reruns and reapplies
  `GRANT CREATE, USAGE ON SCHEMA public` (PG15+ doesn't imply this from
  PGO's own database-level grant). The wait-before-sync ordering matters:
  the schema-grants script covers all 16 dedicated databases in one
  `ON_ERROR_STOP=1` psql invocation, and `aap`/`aap-eda` sit before
  `aap-controller`/`aap-hub` in that list — syncing too early would abort
  the script and leave sibling databases' grants unapplied too.

## Residual risk (flagged, not blocking)

Dropping `aapgateway`/`aapeda` relies on PGO recreating them from the
still-present `zuno-postgresql-pguser-*` "bring your own password"
Secrets rather than generating fresh random passwords - matches this
chart's documented pattern for every other dedicated database, but not
live-verified specifically for a *dropped-then-recreated* role. Watch
Gateway/EDA logs on the first live run for an auth failure (distinct
from `InvalidToken`) if this assumption is wrong.

## Verification checklist

- `make d1 uninstall aap` then `\l`/`\du` via psql confirms `aap`/
  `aap-eda` and `aapgateway`/`aapeda` are gone.
- `make d1 install aap` completes with no `InvalidToken` or "permission
  denied for schema public" in Gateway/EDA logs, no manual intervention.
- `zuno-postgresql-d1`'s `status.operationState` shows a sync triggered
  during the install run.
- `aap-controller`/`aap-hub` schema grants (`\dn+ public`) still intact
  afterward - confirms the ordering fix worked.
