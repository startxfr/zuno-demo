# ADR-0529: Stop the PGO/External-Secrets write loop on pguser secrets

- **Status:** Implemented (2026-08-28) - live-verified on all 17 pguser secrets
- **Target:** v0.4
- **Date:** 2026-08-28
- **Decision owners:** Zuno Demo architecture team

## Context

Every `zuno-postgresql-pguser-<user>` Secret is written by two controllers on
purpose. That is PGO's "bring your own password" mechanism: the chart
pre-creates the Secret from Vault, with PGO's two identifying labels, at
ArgoCD sync-wave `-35` — before the `PostgresCluster` exists at `-30` — so PGO
adopts the Vault password instead of generating one. Consumers in other
namespaces resolve the same Vault path independently, and some run before the
PGO Secret exists, so the credential has to be knowable outside PGO's scope.
This ADR does not change that decision.

What it fixes is that the two controllers were **fighting**, continuously.

External Secrets wrote with `creationPolicy: Orphan`, whose write is
destructive: it replaces `.data` wholesale with the two keys the chart
supplies (`user`, `password`), deleting the `verifier`, `uri`, `jdbc-uri`,
`host`, `port`, `dbname` and `pgbouncer-*` keys PGO maintains on the same
object. PGO re-added them. ESO's `reconcile.external-secrets.io/data-hash`
annotation — the hash of its own two-key view — then permanently disagreed
with the real content, so its `isSecretValid()` never passed and it rewrote on
**every event** rather than on `refreshInterval`.

Measured on the live cluster before the fix:

- the key set flipped between 2 and 12 roughly every 8 seconds, on all 17
  Secrets, indefinitely;
- `data-hash` stayed pinned at `cfef4b90a336081d6d1dd52e0a679def` while the
  content oscillated, which is the direct signature of the mechanism;
- PGO regenerates the verifier whenever it is empty, and SCRAM salting is
  random, so **each cycle produced a different verifier**, pushed to the
  database with `ALTER ROLE`. `pg_authid.rolpassword` for `ragsxalegacy` was
  rewritten every ~10 seconds — four samples, four salts.

The consequences were not cosmetic:

1. **A long-lived client could not survive an hour.** The plaintext password
   never changed, but the salt did, which is enough to invalidate a SCRAM
   session already negotiated. When pgbouncer's 3600s `server_lifetime` forced
   a re-login, it got `password authentication failed`. This is the real cause
   of the ingestion failure recorded in WP-084 on 2026-08-27, which had been
   misattributed first to Postgres pod restarts and then to a credential
   rotation. Any connection outliving `server_lifetime` was exposed, not just
   ingestion.
2. **`ansible/roles/aap/tasks/install.yml` reads `.data.verifier`** from
   `-pguser-aapgateway` and `-pguser-aapeda` to recreate roles. That field was
   present or absent depending on the instant of the read — a coin flip.
3. Continuous etcd write amplification across 17 objects, and continuous DDL
   on `pg_authid` across 17 roles.

## Decision

**1. `creationPolicy: Merge` for all 17 pguser ExternalSecrets**, via a single
`credentials.pguserCreationPolicy` value so they cannot drift apart. Merge
removes and re-adds only its own managed keys, leaving PGO's untouched, so
both controllers' writes become no-ops.

`refreshInterval: 0` was evaluated and **rejected**: it only gates ESO's
`shouldRefresh`, not the `isSecretValid` hash check that actually drove the
loop, and it would additionally break
`ansible/tasks/force_externalsecret_refresh.yml`, whose `force-sync`
annotation works precisely through `shouldRefresh`.

**2. Pre-create the Secrets from Vault in Ansible**, before the
`PostgresCluster` is applied
(`ansible/roles/postgresql/tasks/precreate_pguser_secrets.yml`). Merge does
not create a missing Secret, and the greenfield path is real: uninstall
cascades the `PostgresCluster` and garbage-collects all 17. Without this step
PGO would win the race with a self-generated password `P_pgo`, ESO would merge
Vault's `P_vault` over `password` only, and PGO — seeing a non-empty
`verifier` — would keep `P_pgo` forever. The database would authenticate with
one credential while Vault, the Secret and every cross-namespace consumer
advertised another: silent, permanent divergence.

The bootstrap is strictly create-if-missing and never touches an existing
Secret, the same discipline ADR-0345 established for Vault seeding.

## Consequences

**Rotation becomes explicit, and this is the real trade-off.** Under Orphan,
the constant deletion of `verifier` meant a new Vault password eventually
reached the database on its own. Under Merge the verifier persists, PGO keeps
its `existing` branch, and **writing a new password to Vault no longer reaches
the database**. ADR-0345 already makes non-rotation the desired default, but
the deliberate-rotation runbook must now be followed:

1. `vault kv put` the new value.
2. `ansible/tasks/force_externalsecret_refresh.yml` on the ExternalSecret
   (still works — `refreshInterval` stays `1h`).
3. `oc patch secret zuno-postgresql-pguser-<user> -n zuno-data --type=json
   -p '[{"op":"remove","path":"/data/verifier"}]'` — **the step with no
   equivalent before**, which forces PGO to re-derive the SCRAM verifier from
   the new password and issue the `ALTER ROLE`.
4. Refresh the consumer ExternalSecret in the other namespace.
5. Confirm `pg_authid.rolpassword` changes **once** and then stays put.

Rollback is a single value: `credentials.pguserCreationPolicy: Orphan`. It
restores the previous behaviour exactly — undesirable but known and
non-destructive. The Ansible pre-creation is inert where the Secrets already
exist, so it needs no revert.

## Verification

Pre-flight, before widening: all 17 pguser passwords were verified identical
to their Vault source, so Merge froze a converged state rather than cementing
a divergence.

Piloted on `-pguser-ragsxalegacy` first, with `-pguser-ragtech` left on Orphan
as a control. Over five minutes:

| | pilot (Merge) | control (Orphan) |
|---|---|---|
| `resourceVersion` | frozen at 79430154, all 30 samples | advanced ~17,000 |
| key count | 12 throughout | repeatedly seen at 2 |
| `pg_authid.rolpassword` | one salt across 4 samples/60s | 4 different salts |
| `data-hash` | moved to the full-content hash | pinned at the 2-key hash |

After widening to all 17: zero stripped Secrets and the summed
`resourceVersion` of all 17 completely static over 90 seconds; the md5 of all
17 roles' verifiers identical across 4 samples over 90 seconds; and
`-pguser-aapgateway`/`-pguser-aapeda` `.data.verifier` present on 8 reads out
of 8, where it had been alternating.
