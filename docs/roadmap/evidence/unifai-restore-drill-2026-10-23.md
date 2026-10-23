# UnifAI restore drill on zuno-unifai (2026-10-23)

Real `UnifaiRestore` on the live stack of demo333 (operator 0.1.31, namespace `zuno-unifai`),
coordinated with the sessions that use the cluster. Not a scratch-namespace drill: the live stores
were modified, then restored.

## Method

1. Fresh backups from the hardened CronJob pods (manual Jobs from `unifai-backup-mongodb` and
   `unifai-backup-qdrant`, read-only root filesystem): MongoDB `20261023T214446Z` with its
   `meta.json`, Qdrant `20261023T214445Z` (1 collection). The stack's
   `status.credentialKeyFingerprint` (`69f244d3...`) matches the one in `meta.json`.
2. Counts of both stores (a short Job in the namespace, same query as
   `ansible/roles/unifai/tasks/restore_counts.yml`): 22 Mongo collections, `confluence_data_hybrid`
   501 points, `pipeline_monitoring.metrics` 503 documents.
3. Marked change: one marker document inserted into `pipeline_monitoring.metrics` (504) and one point
   deleted from `confluence_data_hybrid` (500).
4. `UnifaiRestore` with `spec.backup: 20261023T214446Z` (no `spec.source`; credentials read from the
   stack's `spec.backup.s3`).

## Result

- Phases: Stopping (7 applications scaled down), Restoring, Starting, Completed, in about 1 min 40 s
  (`startedAt` 21:51:23Z, `completedAt` 21:53:00Z). `status.restored`:
  `mongodb/20261023T214446Z`, `qdrant/20261023T214445Z`.
- Counts after the restore are identical to the counts before the marked change (diff empty):
  the marker is gone (503) and the deleted point is back (501).
- All applications Ready, the stack Ready, the 12 bundle workflows Ready, a tekos chat answers.
- The restore Job and the hardened backup Jobs ran with the 0.1.31 pod hardening.
- No error-level line in the multiagent log. A side finding is below.

## Side finding (not caused by the restore)

The multiagent backend logs about 3 `401 Unauthorized` per second on
`GET ai-gateway/v1/models`. The caller is the operator (`Go-http-client`): the `unifaillm`
controller reconciles about 4.7 times per second and `unifaiagentbundle` about 1.5 per second, for
at least the last hour (Prometheus `controller_runtime_reconcile_total`), each LLM reconcile calling
`config.validate`, which lists the gateway's models without a token. Harmless for users but a hot
loop; reported to the operator owner.
