# zuno-unifai EgressFirewall rehearsal plan (WP-224 rollout step 6)

Status: plan only. Nothing here has been run. Every cluster step needs the user's go, and the start waits for the
end of the UnifAI canary (a9) and for the golden path and GPU window of other sessions.

## Why

The `zuno-unifai` namespace runs content that agents and users control (RAG sources, git sources, uploaded
documents). Without an egress firewall, a prompt-injected agent can send data to any host. ADR-0602 clause 5 closes
that with deny-all plus an allowlist. The firewall is rendered by `gitops/charts/unifai/templates/egressfirewall.yaml`
and is off (`egress.enabled: false`) because the stack may reach hosts that nobody listed. A missing host fails
silently in a restart path (an ingestion run, a CronJob) days later. The rehearsal finds those hosts before the
switch, on a throwaway stack.

## Where

A throwaway `UnifaiStack` in its own namespace (for example `unifai-fw-rehearsal`), with the same chart values as
`zuno-unifai` plus `egress.enabled: true`. Not `zuno-unifai`, and not the `unifai-e2e-*` or `unifai-operator-canary`
namespaces of a9. Ask a9 for the e2e make targets that create a stack. Delete the namespace at the end.

## Hosts to test

| Host | Used by | How to exercise it |
|---|---|---|
| `keycloak.<domain>` | identity, rag, multiagent | Keycloak login of a persona, token refresh |
| `unifai-identity-<ns>.<domain>` | multiagent, identity, ui | open the UI, list the directory |
| `startxfr.atlassian.net` | rag, rag-celery | ingest one SXSI page through a Confluence source |
| `github.com`, `api.github.com`, `codeload.github.com` | git RAG source (0.1.65) | ingest `startxfr/zuno-demo` (public) through a git source |
| `raw.githubusercontent.com` | RAG source sales-demo | one web ingestion |
| `argo-cd.readthedocs.io`, `helm.sh` | RAG web crawls | one crawl each |
| `docs.redhat.com` | Red Hat books | allowed in the list, but Akamai returns 403 until at least 2026-11-08 15:54 CET: do not fetch, assert only that the rule exists |
| S3 endpoint and bucket | backup CronJob | see Backup below |
| Kubernetes API (6443, control-plane nodes) | rag-server TokenReview | any authenticated RAG query |
| Google (`GOOGLE_APPLICATION_CREDENTIALS`), search API, docling model downloads | unknown | look in the logs of the first restart for `connection refused` or timeouts; add what shows up with a reason line |
| Langfuse (`us.cloud.langfuse.com`) | multiagent | off (`LANGFUSE_ENABLED=false`); only add if turned on |

## Backup

`stack.backup.enabled` is `false` in the chart. The unifai Ansible role adds `stack.backup` when it applies the Application, so the two backup CronJobs exist in
`zuno-unifai`; check the firewall against those applied values, not the chart defaults. The live stack's backup bucket is `zuno-demo222-backups` (eu-west-2, from `zuno_postgresql_backup_s3_*`; the name is
a leftover of demo222, the bucket is still the one in use). `zuno-demo333-backups` (eu-central-1) is the MariaDB bucket. To rehearse:

1. Enable `stack.backup` on the throwaway stack with that bucket and a rehearsal prefix, and the chart's default
   credentials (`postgresql/backup-s3`).
2. Trigger the CronJob once by hand (`oc create job --from=cronjob/...`).
3. Check the object lands and that the firewall allows both the endpoint and the virtual-hosted bucket name.

Ask the user before writing to the real bucket. The rehearsal object is deleted afterwards.

## Scenarios

1. **Baseline.** Stack up with the firewall on; every pod Ready.
2. **Restart paths.** `oc rollout restart` of every Deployment, one at a time, then wait for Ready. Startup is
   where model downloads and discovery calls happen.
3. **Ingestion.** One source of each type: Confluence, git, web (raw.githubusercontent.com, readthedocs, helm.sh).
4. **Query.** A RAG question that cites the ingested documents; a chat through the gateways.
5. **Login.** Keycloak login and refresh, from the UI.
6. **CronJobs.** Backup (above) and any other CronJob in the namespace.
7. **Negative check.** From a pod, `curl https://example.com` fails (the firewall blocks), and DNS still resolves.
8. **Log sweep.** Grep every pod's logs for `connect`, `timeout`, `refused`, `SSL`, `getaddrinfo` since the start.
   Each hit is either a missing host (add it with a `reason`) or noise (note why).

## Pass criteria and switch

- All scenarios pass, with every added host carrying a `reason` line in `gitops/charts/unifai/values.yaml`.
- The `unifai` chart renders and `check_mesh_mtls.py` passes (remove the `EGRESS_DEFERRABLE` entry for zuno-unifai
  in the same commit as the switch).
- A golden path run by the session that owns it, just before the switch.
- Then, with the user's go: `egress.enabled: true`, push, watch `zuno-unifai-d1`, restart one pod as a test.

## Rollback

`oc -n zuno-unifai delete egressfirewall default` takes effect at once. Then set `egress.enabled: false` in git, or
ArgoCD recreates it.

## Coordination

Announce the window to a9 (UnifAI) and b9 before creating the namespace. Keep the throwaway stack light (no GPU, no
new images) so it does not collide with other heavy actions.

## Result

Run on 2026-11-08, see [the evidence file](../roadmap/evidence/wp-224-unifai-firewall-rehearsal-2026-11-08.md).
