# Operations

Operational documentation will cover agent enable/disable, model health, MCP health, RAG refresh, scheduled tasks, user/session support, quotas, costs, logs and tracing.

## UnifAI image admission (ADR-0586, WP-178)

The Sigstore policy-controller (webhook `policy.rhtas.com`, namespace `policy-controller-operator`) checks the keyless signature of every
`quay.io/zuno/unifai-**` image of a pod created in an opted-in namespace (`zuno-unifai`, `unifai-operator`: label `policy.rhtas.com/include=true`).
The policy is `ClusterImagePolicy zuno-unifai-images`; its identities come from `platform/supply-chain/image-identities.yaml` (release workflows
always, the `devel` build only on a cluster that accepts development signatures). Images that match no policy (MongoDB, Qdrant, RabbitMQ, Redis,
Temporal, docling, the backup Jobs) are only reported (`no-match-policy: warn`). zuno's own verifier and drift check
(`make d2 check unifai`) stay the main guard: the admission is the second one, at the cluster.

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

## Rolling a UnifAI release, and taking over a roll (WP-176, WP-178)

Operator and application images move in two separate steps, always in this order, each with the user's go and with the owner of any running measurement (stresstest, ranking set) agreeing that no UnifAI pod may restart.

1. **Operator.** The release owner publishes the operator, bundle and catalog digests once its CI and canary are green. From a detached worktree on `origin/devel` with `ansible/confidential.yml` copied in: `python3 platform/supply-chain/pin_operator_catalog.py latest --version X.Y.Z --dry-run` (signatures with the release identity, then the admission preflight), the same without `--dry-run`, commit and push only that commit, then `make d2 install unifai` and `make d2 check unifai`. Only the operator controller restarts. Rolled so far on demo333: 0.1.42 to 0.1.45 and 0.1.47 (0.1.46 was never released).
2. **Application images, one roll.** `python3 platform/supply-chain/pin_unifai_images.py devel-<sha> --accept-dev --dry-run`, then the real pin, then a single `make d2 install unifai`: this restarts the UnifAI pods, so batch every stack change (chart values, CR fields) into the same roll. Settings that a release adds but a measurement owner switches on one by one (ranking `spec.rag.search`, `spec.rag.reranker`, `resyncToken`) stay unset in that roll.
3. **Check.** `make d2 check unifai`, the webhook log (`policy-controller-operator`) for refusals, and the release owner's read-only proofs (digests, environment of the pods).
   **Catalog tags (found 2026-10-31).** A catalog digest that carries only the moving tag `latest` is garbage-collected by quay, signature tags included, as soon as `latest` moves to the next release: the CatalogSource pod can then no longer be rescheduled, a rollback is impossible and `make d2 check unifai` fails on the signature of the pinned catalog. Since the fork's fix (devel 8d492f981) each release also pushes `unifai-operator-catalog:v<VERSION>`, which keeps its digest. A catalog released before that fix (0.1.48) needs the tag `v<VERSION>` pushed on its digest by someone with quay write rights before the next release; until then bump to the newest catalog quickly after a release.
4. **Rollback.** Re-pin the previous digests and run `make d2 install unifai` again; a stack field added in the roll is removed by dropping it from the chart values.

When the session that owned a roll has disappeared (no entry in the session list), nothing was handed over unless it is committed on `origin/devel`: re-derive the pins with the dry-run, ask the release owner for the CR fields and the settings that must stay unset, and take the user's go again before touching the cluster. A peer's message is information, not the user's approval.

## Moving a PostgreSQL role onto the shared demo password (ADR-0595, ADR-0529)

A new value of `zuno_admin_*_postgresql_*_password` reaches a fresh install only. On a running cluster the Vault path already
exists (ADR-0345 seeds only missing paths) and PGO keeps the SCRAM verifier it derived from the old password (ADR-0529). One role
at a time, with the cluster owner's go for each:

1. Set the new value in `ansible/confidential.yml` (the per-component variable, or the shared `zuno_admin_mainpwd`).
2. Overwrite the Vault path, not delete it: `vault kv put zuno/<path> username=<user> password=<value>` (the paths are the keys of
   `_vault_generated_secrets` in `ansible/roles/vault/tasks/install.yml`; keep the existing `username`).
3. `ansible/tasks/force_externalsecret_refresh.yml` on the ExternalSecret that reads the path.
4. Remove the verifier so PGO re-derives it and issues the `ALTER ROLE`:
   `oc patch secret zuno-postgresql-pguser-<user> -n zuno-data --type=json -p '[{"op":"remove","path":"/data/verifier"}]'`.
5. Refresh the consumer ExternalSecret in the other namespace, then confirm the consumers reconnect and that
   `pg_authid.rolpassword` changed once and stays put.

Done live on demo333 on 2026-11-03 (eleven roles, then Redis): `mlflow` first as the canary, then OGX, MaaS and the six AAP roles,
then `keycloak` and `zunoapp`. Traps seen on the way:

- Removing the verifier too early leaves it derived from the OLD password: the ExternalSecret may not have rewritten `password` yet
  when PGO regenerates it (`aapcontroller` kept its old hash). Wait until `password` carries the new value, then remove the
  verifier; if `pg_authid.rolpassword` did not change, remove it a second time.
- The AAP operators keep their own copies, `aap-*-postgres-configuration` (controller, eda, eda-event-stream, hub, metrics),
  and do not refresh them when `aap-*-postgres-config` changes. Patch their `password` from the source Secret, then restart the
  AAP workloads, or the pods fail with `password authentication failed`.
- Keycloak reads its database Secret at start: delete `zuno-0` after the role changed. Redis (`zuno-redis-master`) and the
  ai-gateway read theirs at start too: refresh both ExternalSecrets, restart Redis, then the ai-gateway.
- maas-controller copies `maas-db-config` into `redhat-ai-gateway-infra` once and never updates it. Missed on 2026-11-03,
  maas-api crash-looped the next morning on `password authentication failed for user "maas"`. `make d1 check openshift-ai`
  reports the stale copy and `make d1 reconcile openshift-ai` resyncs it: it deletes the copy, restarts maas-controller (a
  delete alone is not recreated), waits for the new copy to match its source, then restarts maas-api.

Not rotated: the MariaDB users (`mlpipeline`, `mlops`, `trillian`) live on the simulated external instance `zuno-ext-sim/ext-mariadb`
of the frozen WP-143 pilot, whose credentials are not ours (ADR-0352); `aap/admin` is an AAP console password, not a database.