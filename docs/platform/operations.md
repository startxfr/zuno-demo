# Operations

Operational documentation will cover agent enable/disable, model health, MCP health, RAG refresh, scheduled tasks, user/session support, quotas, costs, logs and tracing.

## UnifAI image admission (ADR-0586, WP-178)

The Sigstore policy-controller (webhook `policy.rhtas.com`, namespace `policy-controller-operator`) checks the keyless signature of every
`quay.io/zuno/unifai-**` image of a pod created in an opted-in namespace (`zuno-unifai`, `unifai-operator`: label `policy.rhtas.com/include=true`).
The policy is `ClusterImagePolicy zuno-unifai-images`; its identities come from `platform/supply-chain/image-identities.yaml` (release workflows
always, the `devel` build only on a cluster that accepts development signatures). When `zuno_unifai_signature_mirror_host` is set in the cluster
file (WP-248), the signatures are read from the internal registry and the policy is split into one `ClusterImagePolicy` per repository,
`zuno-unifai-images-<repository>` (the webhook accepts one signature source per authority; exact globs, because `unifai-operator**` would also
catch the bundle and the catalog). Images that match no policy (MongoDB, Qdrant, RabbitMQ, Redis,
Temporal, docling, the backup Jobs) are only reported (`no-match-policy: warn`). zuno's own verifier and drift check
(`make d2 check unifai`) stay the main guard: the admission is the second one, at the cluster.

### Copy before pin (WP-248)

With `zuno_unifai_signature_mirror_host` set, the admission policies read the signatures from the internal Quay. A release must be
copied there before its pin is rolled (`python3 platform/supply-chain/mirror_unifai_images.py --to <registry>/zuno --version <x.y.z>`,
the push robot's `DOCKER_CONFIG`, `QUAY_API_TOKEN` for public repositories). `make d2 install unifai` checks it before it applies anything
(`platform/supply-chain/check_unifai_in_registry.py`, anonymous and read-only: each pinned digest and its `.sig` tag) and stops with the
list of what is missing, instead of leaving the pods refused.

### Look at it

```
oc get clusterimagepolicies.policy.sigstore.dev zuno-unifai-images -o jsonpath='{.spec.mode}{"\n"}'   # warn or enforce
oc get ns -l policy.rhtas.com/include=true
oc logs -n policy-controller-operator deploy/zuno-policy-controller-webhook --since=24h | \
  grep -E "Failed to validate at least one policy for quay.io/zuno/unifai|no matching policies for image quay.io/zuno"
```

Use the full resource name `clusterimagepolicies.policy.sigstore.dev`: a bare `clusterimagepolicy` also names OpenShift's own resource.
A line in the webhook log names the namespace, the pod and the image. In `warn` it is an admission warning (the pod was created); in
`enforce` the pod creation was refused (`oc get events -n <namespace>` shows `admission webhook "policy.rhtas.com" denied the request`).

### Warn or enforce

The mode is a cluster variable: `zuno_unifai_admission_mode` (default `warn`) in `ansible/clusters/<cluster>.yml`, applied by
`make d1 install rhtas-config`. `zuno_unifai_admission_enabled: false` removes the policy and the labels. Only the UnifAI policy changes mode:
the first-party policy `zuno-first-party-images` stays in `warn`. A new cluster gets the policy in `warn`.

### A legitimate pod is refused (break-glass)

1. Find the reason in the event or the webhook log. Most often the image is not signed by an identity of `image-identities.yaml` (a hand-built
   image, a branch build on a cluster that does not accept development builds) or it was signed only in the Ed25519 Rekor v2 log, which the
   controller cannot read (zuno's verifier accepts it, the admission does not).
2. Unblock at once, without a deployment: `oc label namespace <namespace> policy.rhtas.com/include-` removes the namespace from the
   webhook (undo with `oc label namespace <namespace> policy.rhtas.com/include=true`, or re-run `make d1 install rhtas-config`, which labels it again).
   Or switch the cluster to `warn` and re-run the install.
3. Fix the cause: pin a CI-built signed digest (`python3 platform/supply-chain/pin_unifai_images.py devel-<sha> --accept-dev`) and apply it with
   `make d2 install unifai`.

### Before a pin

`pin_unifai_images.py` and `pin_operator_catalog.py` verify the digests offline, then send them through the cluster's webhook (a server-side
dry-run Pod in `zuno-unifai`, `platform/supply-chain/admission_preflight.py`). A digest that cosign accepts but the webhook warns about or
refuses stops the pin, with the webhook's own message. When the cluster cannot answer, the step is skipped with a notice;
`--no-admission-preflight` skips it on purpose.

### Limits

- The webhook has `failurePolicy: Ignore` and one replica: if it is down or slower than its 10 s timeout, pods are admitted without a check
  (fail-open). Protection is best-effort; the verifier and the drift check do not depend on it.
- The controller only reads ECDSA transparency-log keys. The trusted root also lists an Ed25519 key (Rekor v2, `log2025-1`): a signature logged only
  there verifies with cosign but not at admission. The pin preflight catches it before a rollout. Re-check when the policy-controller
  supports Ed25519, or if the fork's CI moves to a cosign that signs into Rekor v2.
- Attestations (provenance, SBOM) are not checked at admission: an attestation of an expired Fulcio certificate needs a Rekor lookup. zuno's
  verifier checks them before the stack is applied.
- The trust root is rendered offline from `platform/okf/sigstore/trusted_root.json` (`platform/supply-chain/render_policy_trustroot.py`; CI checks it
  is up to date). After a Sigstore root rotation, regenerate it and re-run `make d1 install rhtas-config`.

## Large Red Hat images in Quay (WP-261, ADR-0612 family e)

The eight largest Red Hat product images the demo runs (`platform/supply-chain/mirrored-redhat-images.yaml`) are copied
into **private** repositories of the internal Quay, `zuno/redhat/<path>`, and redirected by the ImageDigestMirrorSet
`zuno-redhat-via-registry`; the nodes read them with the `zuno+pull` robot of the global pull secret
(`zuno_quay_node_pull_secret`). Never make these repositories public: the route is reachable from the Internet.

- **After an RHOAI, AAP or Lightspeed upgrade:** `python3 platform/supply-chain/mirror_redhat_images.py --drift` lists the
  running digests the list misses. Add them (keep the old digests until the upgrade is over), then copy:
  `DOCKER_CONFIG=~/.config/zuno/quay-push QUAY_API_TOKEN=<admin token> python3 platform/supply-chain/mirror_redhat_images.py --to <registry host>`.
  Until then the new pods pull from `registry.redhat.io`, slower but working (fallback).
  The copy takes every architecture of an index and sends one layer at a time (a PUT of several GB from the workstation
  was cut after about ten minutes when layers went in parallel): count about 2 h for the full list at 9 MB/s.
- **Never remove a source from that ImageDigestMirrorSet** outside an announced drain window: removal drains every node.
  To stop using an entry, stop copying it, or delete its repository in Quay (404, the nodes fall back).

## Rolling a UnifAI release, and taking over a roll (WP-176, WP-178)

Operator and application images move in two separate steps, always in this order, each with the user's go and with the owner of any running measurement (stresstest, ranking set) agreeing that no UnifAI pod may restart.

1. **Operator.** The release owner publishes the operator, bundle and catalog digests once its CI and canary are green. From a detached worktree on `origin/devel` with `ansible/confidential.yml` copied in: `python3 platform/supply-chain/pin_operator_catalog.py latest --version X.Y.Z --dry-run` (signatures with the release identity, then the admission preflight), the same without `--dry-run`, commit and push only that commit, then `make d2 install unifai` and `make d2 check unifai`. Only the operator controller restarts. Rolled so far on demo333: 0.1.42 to 0.1.45 and 0.1.47 (0.1.46 was never released).
2. **Application images, one roll.** `python3 platform/supply-chain/pin_unifai_images.py devel-<sha> --accept-dev --dry-run`, then the real pin, then a single `make d2 install unifai`: this restarts the UnifAI pods, so batch every stack change (chart values, CR fields) into the same roll. Settings that a release adds but a measurement owner switches on one by one (ranking `spec.rag.search`, `spec.rag.reranker`, `resyncToken`) stay unset in that roll.
3. **Check.** `make d2 check unifai`, the webhook log (`policy-controller-operator`) for refusals, and the release owner's read-only proofs (digests, environment of the pods).
   **Catalog tags (found 2026-10-31).** A catalog digest that carries only the moving tag `latest` is garbage-collected by quay, signature tags included, as soon as `latest` moves to the next release: the CatalogSource pod can then no longer be rescheduled, a rollback is impossible and `make d2 check unifai` fails on the signature of the pinned catalog. Since the fork's fix (devel 8d492f981) each release also pushes `unifai-operator-catalog:v<VERSION>`, which keeps its digest. A catalog released before that fix (0.1.48) needs the tag `v<VERSION>` pushed on its digest by someone with quay write rights before the next release; until then bump to the newest catalog quickly after a release.
4. **Rollback.** Re-pin the previous digests and run `make d2 install unifai` again; a stack field added in the roll is removed by dropping it from the chart values.

When the session that owned a roll has disappeared (no entry in the session list), nothing was handed over unless it is committed on `origin/devel`: re-derive the pins with the dry-run, ask the release owner for the CR fields and the settings that must stay unset, and take the user's go again before touching the cluster. A peer's message is information, not the user's approval.

## The Day-1 entry gate (ADR-0352 clause 10)

`make d1 install` refuses to start while a vital Day-0 component is not functional: argocd, vault, external_secrets,
cert_manager, postgresql, keycloak, aap or aap_config. The run then stops before applying anything of Day 1. It prints
each failing component with its findings and the fix (`make d0 reconcile <component>`). `make d0 check all` gives the full
report. The gate costs about 80 s per run. For a rehearsal on a cluster whose Day 0 is knowingly partial, skip it with
`EXTRA_VARS='-e zuno_day1_vital_gate=false'`; the skip is printed in the run.

## Security profiles: demo and hardened (ADR-0602, WP-223)

`zuno_security_profile` (in `ansible/inventories/demo/group_vars/all/main.yml`, overridable in `ansible/clusters/<cluster>.yml`
or `ansible/confidential.yml`) picks one of two credential schemes. `ansible/tasks/assert_security_profile.yml` rejects any
other value. demo333 runs `demo`.

| | `demo` (default) | `hardened` |
|---|---|---|
| Infra passwords (Keycloak master accounts, AAP, every PostgreSQL role, MariaDB, mlops DB, RHTAS Trillian, Redis) | the shared `zuno_admin_mainpwd` (ADR-0595), or md5 of the seed when it is unset | random, generated by the consumer on first seed, stored only in Vault |
| Dify administrator | shared password followed by `1` | random (ends with `1`, Dify wants a digit) |
| OpenClaw Control UI | shared persona password | random per persona |
| Personas (humans, eval and stress twins) | shared `zuno_personas_mainpwd` | the same shared value, which must exist (no md5 fallback), be at least 12 characters and contain a digit |
| md5 fallback | used when the shared value is unset | never computed: the run fails with a hint |
| MCP Gateway workload token | random (both profiles since WP-223; no longer `token-<admin password>`) | random |
| Keycloak `zuno` realm | brute-force detection (30 failures, 60 s steps, 15 min ceiling, never permanent) | the same, plus `passwordPolicy` `length(12) and digits(1) and notUsername`, a 1 h idle session (10 h maximum unchanged), and TOTP enrolment for the master console administrator `zuno-admin` |

A per-component variable set explicitly in `ansible/confidential.yml` still wins in `hardened` (a deliberate choice, never a
derivation). In `hardened`, read an admin password from Vault, never from the inventory:
`vault kv get -field=password zuno/keycloak/console` (Keycloak console, user `zuno-admin`), `zuno/aap/admin` (AAP), `zuno/dify/admin`,
`zuno/openclaw/<persona>` (field `ui_password`), `zuno/<path>` for a database (the keys of `_vault_generated_secrets` in
`ansible/roles/vault/tasks/install.yml`).

Switching profile on a seeded cluster moves no password: every Vault path is seed-only-if-missing (ADR-0345), so `hardened` is a
fresh-install choice, or a per-path rotation with the runbook below. The Keycloak realm settings follow the profile on the next
`make d0 install keycloak` (the client-reconcile Job merges `realm-settings.json`); going back to `demo` does not remove the
password policy or restore the 8 h idle timeout - clear them in the admin console if needed.

The shared personas and admin values (Keycloak, Dify, Vault copies) have their own runbook: [Rotating the shared demo password](shared-password-rotation.md).

## Moving a PostgreSQL role onto the shared demo password (ADR-0595, ADR-0529)

A new value of `zuno_admin_*_postgresql_*_password` reaches a fresh install only. On a running cluster the Vault path already
exists (ADR-0345 seeds only missing paths) and PGO keeps the SCRAM verifier it derived from the old password (ADR-0529). The 13
pguser roles of `zuno-data` and the session-store Redis therefore move one at a time, in a window announced to the other sessions
and with the cluster owner's go.

Before the window:

- Patroni shows 3 members, both replicas `streaming` on the leader's timeline at lag 0 (`patronictl list` in the leader's
  `database` container). A failover during the window then lands on a replica that already holds the new verifiers.
- PGO, External Secrets and the AAP operators have not restarted in the last 15 minutes. Under etcd load they lose leader
  election and crash-loop (2026-11-13), and then miss the reconcile that each step waits for.
- No node is in DiskPressure: an eviction in the middle of a phase looks like a rotation failure.

For each role:

1. Set the new value in `ansible/confidential.yml` (the per-component variable, or the shared `zuno_admin_mainpwd`).
2. Patch the `password` of the Vault path and keep its `username`: `vault kv patch -method=rw zuno/<path> password=-`, with the
   value on stdin and never on a command line (ADR-0603 M9; `ansible/tasks/vault_cli.yml` does the same from a playbook). The
   paths are the keys of `_vault_generated_secrets` in `ansible/roles/vault/tasks/install.yml`. Log in as `ansible-seeder`
   (`ansible/tasks/vault_login.yml`) and select the server pod with `-l app.kubernetes.io/name=vault,component=server`: the
   backup and snapshot Job pods also carry `app.kubernetes.io/name=vault`.
3. Run `ansible/tasks/force_externalsecret_refresh.yml` on `zuno-postgresql-pguser-<role>` and wait until its `password` holds
   the new value.
4. Remove the verifier so PGO re-derives it and issues the `ALTER ROLE`:
   `oc patch secret zuno-postgresql-pguser-<role> -n zuno-data --type=json -p '[{"op":"remove","path":"/data/verifier"}]'`.
   Confirm that `md5(rolpassword)` in `pg_authid` changed (compare the hashes, never print them).
5. Test the login on the leader: `psql "host=localhost dbname=postgres user=<role> sslmode=require"`, with `PGPASSWORD` read
   from stdin (`pg_hba` accepts only `hostssl ... scram-sha-256`). The new value must connect and the old one must be refused.
6. Refresh the consumer ExternalSecret (table below), restart the consumer, and check its log for
   `password authentication failed`.

| Role | Consumer Secret, after `zuno-postgresql-pguser-<role>` | Restart |
|---|---|---|
| `mlflow` | `redhat-ods-applications/mlflow-backend-store` (`uri`) | `deploy/mlflow` |
| `zunoapp` | none | none |
| `ogxserver` | `redhat-ods-applications/ogx-pgvector-password` | `deploy/zuno-ogx` |
| `kagent` | `zuno-kagent/kagent-database` (`url`) | `deploy/kagent-controller` |
| `dify` | `zuno-dify/dify-app` (`DB_PASSWORD`) | `dify-api`, `dify-worker`, `dify-beat`, `dify-plugin-daemon` |
| `maas` | `redhat-ods-applications/maas-db-config`, then its copy in `redhat-ai-gateway-infra` | the `make d1 reconcile openshift-ai` steps (below) |
| `aapgateway`, `aapcontroller`, `aaphub`, `aapeda`, `metricsservice`, `msawxreadonly` | `zuno-aap/aap-{gateway,controller,hub,eda,metrics}-postgres-config` and `aap-metrics-read-config`, then the operator copies (below) | the five AAP operators, then the 14 AAP workloads |
| `keycloak` | `zuno-auth/keycloak-postgresql-app` | `sts/zuno` (pod `zuno-0`) |
| Redis, `zuno/redis/session-store` | `zuno-auth/zuno-redis-auth` and `zuno-ai-run/ai-gateway-redis-credentials` | `sts/zuno-redis-master`, then `deploy/ai-gateway` |

The order that worked: `mlflow` as the canary; then `zunoapp`, `ogxserver`, `kagent`, `dify` and `maas`; then Redis; then the
six AAP roles (AAP is down 5-15 minutes); `keycloak` last (SSO is down 30-65 seconds).

Done live on demo333 twice:

- 2026-11-03: eleven roles, then Redis: `mlflow` first as the canary, then OGX, MaaS, the six AAP roles, `keycloak` and
  `zunoapp`.
- 2026-11-13: all 13 roles and Redis, in the order above, about 25 minutes of phase run time. Afterwards, a scan of every Secret
  found no key still holding the old value, the golden path passed, and `make d3 check recovery` was ok.

Traps seen on the way:

- Removing the verifier too early leaves it derived from the OLD password: the ExternalSecret may not have rewritten `password` yet
  when PGO regenerates it (`aapcontroller` kept its old hash). Wait until `password` holds the new value, then remove the
  verifier; if `pg_authid.rolpassword` did not change, remove it a second time.
- The AAP operators keep their own copies, `aap-*-postgres-configuration` (controller, eda, eda-event-stream, hub, metrics),
  and do not refresh them when `aap-*-postgres-config` changes. Patch their `password` from the source Secret, then restart the
  five AAP operators. They rebuild `aap-controller-app-credentials` (`credentials.py`) and `aap-hub-server` (`settings.py`). Wait
  until both hold the new value before restarting the 14 AAP workloads, or the pods fail with
  `password authentication failed`. On 2026-11-13 the files were rebuilt on the first try; on 2026-11-03 the Hub took about
  6 minutes.
- Keycloak reads its database Secret at start: delete `zuno-0` after the role changed. Redis (`zuno-redis-master`) and the
  ai-gateway read theirs at start too: refresh both ExternalSecrets, restart Redis, check `AUTH` with the new value, then restart
  the ai-gateway.
- The Redis volume is pinned to its zone. Since the masters stopped taking workloads (`mastersSchedulable=false`), a Redis pod
  still on a master moves to a worker in the same zone when it restarts, and the EBS reattach adds about a minute.
- maas-controller copies `maas-db-config` into `redhat-ai-gateway-infra` once and never updates it. Missed on 2026-11-03,
  maas-api crash-looped the next morning on `password authentication failed for user "maas"`. `make d1 check openshift-ai`
  reports the stale copy and `make d1 reconcile openshift-ai` resyncs it: it deletes the copy, restarts maas-controller (a
  delete alone is not recreated), waits for the new copy to match its source, then restarts maas-api.
- Restart by deleting the pods. Argo CD selfHeal reverts the `restartedAt` annotation of `oc rollout restart`. Delete only the
  pods the workload owns: the maas-api label selector also matches the pods of the `maas-api-key-cleanup` CronJob.
- The mlflow operator rolls `deploy/mlflow` again by itself once `mlflow-backend-store` changes. A second new pod right after
  the restart is expected.

Not rotated here:

- The MariaDB users (`mlpipeline`, `mlops`, `trillian`) live on the simulated external instance `zuno-ext-sim/ext-mariadb` of
  the frozen WP-143 pilot, whose credentials are not ours (ADR-0352).
- `aap/admin` is an AAP console password, not a database role.
- `aap-rhn-credentials` (`zuno/aap/rhn`) is the platform owner's Red Hat account. Change the password at Red Hat first, then
  set `zuno_aap_rhn_password` and patch the Vault path.

## Handing out MaaS API keys: what the token limit does and does not cover (WP-220)

Users create their own keys in the MaaS consumer portal, `https://rh-ai.<domain>/maas-consumer-portal` ("API keys"), on the subscription their
group holds (`gpt-oss-20b-ocp-ai-dev`, `-ocp-ai-ops`, `-ocp-paas-ops`, 5,000,000 tokens per hour each).

- **The token limit counts OpenAI-format calls only.** MaaS 3.6 limits `/v1/chat/completions` and `/v1/embeddings` by reading `usage.total_tokens`.
  A key used on the Anthropic Messages path (`/v1/messages`, which is what Claude Code uses) is authenticated and authorised, but it is **not**
  token-limited: Anthropic replies carry no `total_tokens`. Measured on demo333: about 72,000 Anthropic tokens did not move the Limitador counter.
  Do not present the 5,000,000 figure as a ceiling for such a key. Metering that path is WP-225; blocking it is not planned (WP-220 uses it on purpose).
- **The playground's MCP connection needs the user's own OpenShift token** (`https://oauth-openshift.<domain>/oauth/token/request`, valid 24 hours).
  Which tools the user sees depends on their group: `ocp-ai-ops` gets all nine, `ocp-ai-dev` gets none (`tool-policy.yaml`).

## After a node drain or a reboot: `make d3 check recovery`

Read-only (`platform/recovery/check_recovery.py`, `oc` logged in). It lists the layers in the order they have to recover and the next
step for each: nodes Ready and uncordoned (a drain stuck on a single-replica PodDisruptionBudget passes when the pods are deleted,
ADR-0101), MachineConfigPools Updated, ClusterOperators, stuck pods, Quay Ready (answering 401 on its route), the Service
`kuadrant-operator-wasm` with an endpoint and Authorino Ready, and a MaaS route answering 401 without a token (503 = the Kuadrant
wasm-shim failed closed: delete the `maas-default-gateway` pod once the operator is back), and the node-pool layout of
ADR-0614 (masters unschedulable, no workload pod left on a master, the infra pool at 3 Ready nodes). Removing a source from an
ImageDigestMirrorSet drains every node (adding one does not); run it after such a change and after any reboot.

## Node pools (ADR-0614)

Masters run only the control plane. Three infra nodes (`zuno-infra-a/b/c`, tainted `node-role.kubernetes.io/infra`) run the
Red Hat infra-eligible set: default router, internal registry, platform and user-workload monitoring, OpenShift GitOps, Quay.
Three general workers (`zuno-worker-a/b/c`, 200 GB) run everything else; Spot workers (`zuno-worker-spot-a/b/c`) start
from zero when pods are Pending. The two GPU nodes run only model pods and are never scaled down, replaced or drained
without the owner's double approval. To replace a worker: scale its MachineSet to 2, wait for the new node, annotate the
old Machine `machine.openshift.io/delete-machine=true`, scale back to 1 (the Machine API drains it); delete Keycloak `zuno-0`
if it is the last pod holding the drain (ADR-0101). a2a-gateway and Limitador stay at one replica (owner, 2026-11-14) and
the drain evicts them by itself: a2a-gateway's budget is `maxUnavailable: 1`, Limitador has none. Evicting a2a-gateway
drops its open tasks and pending approvals; evicting Limitador resets the rate-limit and token counters. The ai-gateway
runs two replicas: read its log with `oc logs -l app.kubernetes.io/name=ai-gateway -c ai-gateway --tail=-1`, not
`deploy/ai-gateway`.

## A PostgreSQL replica stuck in archive recovery

Symptom: `patronictl list` (leader's `database` container, namespace `zuno-data`) shows a replica that never reaches
`streaming`, and its log repeats `[045] duplicates found for WAL segment ... are multiple primaries archiving to this
stanza?`. Cause: archive-push writes every WAL segment to both pgBackRest repositories (repo1, the local PVC, and repo2,
S3), and PGO's `restore_command` (`pgbackrest --stanza=db archive-get %f "%p"`, no `--repo`) refuses a segment found in
both. PGO owns that parameter: the CRD refuses it in `spec.config.parameters`, it ignores it under
`spec.patroni.dynamicConfiguration`, and it puts its own value back over a `patronictl edit-config`. Seen on demo333 on
2026-11-13, where `patronictl reinit` alone did not help: the re-cloned replica replayed from the archive and hit the
same refusal. With the owner's go, point recovery at repo1 for as long as the replica needs it, in the leader's
`database` container: `patronictl edit-config --force -p 'restore_command=pgbackrest --stanza=db archive-get --repo=1 %f "%p"'`.
Nothing to revert afterwards: PGO restores its value at its next reconcile. No durable fix is decided.

