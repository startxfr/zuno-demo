# Vault: AWS KMS auto-unseal, raft storage, TLS (ADR-0602 clause 1, WP-223)

What changed, what an operator prepares, and how a Vault installed before
WP-223 is migrated with `ansible/playbooks/vault_migrate_kms_raft.yml`.

## What changed

| | Before WP-223 | Now |
|---|---|---|
| Storage | `file` on `data-zuno-vault-0` | integrated `raft` at `/vault/data/raft` on the same PVC, 1 replica, `retry_join` ready for 3 |
| Seal | Shamir, 1 key share | `awskms` (auto-unseal); recovery keys 3 shares / threshold 2 |
| After a pod restart | sealed until a human re-ran the unseal Job | unseals by itself |
| Unseal key and root token | Secrets `vault-bootstrap-credentials` and `vault-unseal-configure-credentials` in `zuno-vault` | no copy in the cluster; init JSON written once to `ansible/vault-recovery-<cluster>.json` (0600, gitignored) on the Ansible controller |
| Root token | used by every seeding role | used once to bootstrap `vault-configurator`, then revoked |
| Configure Job | `vault-unseal-configure`, root token | `vault-configure`, Kubernetes auth as ServiceAccount `vault-configure` (role `vault-configurator`, no KV access) |
| Ansible seed tasks | root token | `ansible/tasks/vault_login.yml`: role `ansible-seeder`, 1h token |
| External Secrets | one `eso-reader` role, read `zuno/data/*` | one `ns-<namespace>` role per namespace from `platform/vault/secret-access.yaml` |
| Listener | `http`, `tls_disable = true` | `https`, certificate from the OpenShift service CA (Secret `vault-tls`) |
| Route | always on, edge | off by default; reencrypt, optional `ip_whitelist` |
| Backups | CSI VolumeSnapshot | CSI VolumeSnapshot + `vault operator raft snapshot` CronJob |

Clients moved to `https://zuno-vault.zuno-vault.svc:8200`: the three
cert-manager ClusterIssuers (`vault-issuer`, `vault-issuer-istio`,
`vault-issuer-mariadb`, with `caBundle` = the service CA, chart value
`vaultCaBundle`), the External Secrets SecretStores (`caProvider` =
ConfigMap `openshift-service-ca.crt`), the configure Job, the raft snapshot
CronJob and `platform/supply-chain/sign_in_cluster.py`. The service CA
rotates about once a year with an overlap period: after a rotation re-run
`make d0 install cert-manager`, `make d1 install service-mesh` and
`make d1 install mariadb` so the ClusterIssuers carry the new bundle (pods
and SecretStores pick the new CA up on their own).

## Prerequisites (operator, once per cluster)

1. **KMS key.** AWS console, KMS, Create key: symmetric, "Encrypt and
   decrypt", single-Region, in the cluster's region. Alias
   `alias/zuno-<cluster>-vault-unseal`. Key administrators: your admin
   role only. Key users: none yet (the IAM user below gets access through
   its own policy, which works with the default key policy that delegates
   to IAM). Copy the key ARN.
   Equivalent CLI:
   ```sh
   aws kms create-key --region eu-west-1 \
     --description "zuno <cluster> Vault auto-unseal" \
     --key-usage ENCRYPT_DECRYPT --key-spec SYMMETRIC_DEFAULT
   aws kms create-alias --region eu-west-1 \
     --alias-name alias/zuno-<cluster>-vault-unseal --target-key-id <key-id>
   ```
   Never schedule this key for deletion: every raft snapshot and CSI
   snapshot of this Vault is unreadable without it. Enabling automatic key
   rotation is safe (KMS keeps the old key material for decryption).
2. **IAM user** `zuno-<cluster>-vault-kms`, programmatic access only, with
   exactly this inline policy and nothing else:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "VaultAutoUnseal",
         "Effect": "Allow",
         "Action": ["kms:Encrypt", "kms:Decrypt", "kms:DescribeKey"],
         "Resource": "arn:aws:kms:<region>:<account-id>:key/<key-id>"
       }
     ]
   }
   ```
   Create an access key (the secret is shown once).
3. **`ansible/confidential.yml`**: fill in the block "Vault auto-unseal with
   AWS KMS" (`zuno_vault_kms_key_id`, `zuno_vault_kms_region`,
   `zuno_vault_kms_access_key_id`, `zuno_vault_kms_secret_access_key`).
   `make d0 install vault` stops if one is missing. The IAM credentials go
   to the Secret `zuno-vault/vault-aws-kms`; the key ARN and region go into
   the `zuno-vault-d1` Application's values.

A fresh cluster needs nothing else: `make d0 install vault` initializes
Vault with recovery keys, writes `ansible/vault-recovery-<cluster>.json`,
bootstraps the identities and revokes the root token. Move that file into
the operators' password manager (split the three shares across people)
and delete it from the controller.

## Migrating a Vault installed before WP-223

`make d0 install vault` refuses to run while
`zuno-vault/vault-bootstrap-credentials` exists - applying the new chart
over the old layout would start an empty raft Vault. The chart itself also
refuses to render without `vault.kms.keyId`, so the new revision reaching
the cluster's `targetRevision` before the migration makes the
`zuno-vault-d1` Application fail with a ComparisonError instead of
changing anything; the running Vault keeps serving (the StatefulSet is
`OnDelete`). Plan the migration together with the merge.

Expected downtime of Vault: steps 2 to 5, typically 10 to 20 minutes.
External Secrets keep the last synced Secrets during the window; new
certificate issuance and seeding wait.

```sh
oc login ...   # cluster-admin
ansible-playbook -i ansible/inventories/demo/hosts.yml \
  ansible/playbooks/vault_migrate_kms_raft.yml
# optional: also rekey the recovery keys to 3 shares / threshold 2 (step 8)
#   -e vault_migrate_rekey_recovery=true
```

The playbook pauses before each step (Enter continues, Ctrl-C then A
aborts):

| Step | Does | Proves |
|---|---|---|
| 0 prechecks | reads the legacy Secret (unseal key, root token), `vault status`, a probe KV value | initialized, unsealed, `storage_type=file`, `type=shamir`, KMS values present |
| 1 snapshot | VolumeSnapshot `vault-pre-kms-raft-<timestamp>` of `data-zuno-vault-0` (not pruned by the daily CronJob) | `readyToUse: true` - the rollback point |
| 2 stop | removes `syncPolicy.automated` from `zuno-vault-d1`, scales the StatefulSet to 0 | pod gone, volume released |
| 3 storage | Job `vault-migrate` on the same PVC: moves the file backend into `/vault/data/file-legacy`, runs `vault operator migrate` (`storage_source "file"` -> `storage_destination "raft"` at `/vault/data/raft`, `node_id zuno-vault-0`, `cluster_addr https://zuno-vault-0.zuno-vault-internal:8201`) | Job succeeded, log shown |
| 4 raft | applies the Application with raft + TLS + `vault.seal.type: shamir` (restores auto-sync), `vault operator unseal <old key>` | `storage_type=raft`, probe value identical |
| 5 seal | applies `vault.seal.type: awskms`, deletes the pod (OnDelete), `vault operator unseal -migrate <old key>`, writes the recovery file, deletes the pod again | `type=awskms`, `recovery_seal=true`, unsealed by itself after a restart, probe identical |
| 6 identities | bootstraps `vault-configurator` with the old root token, runs the `vault-configure` Job, logs in as `ansible-seeder` | the probe is readable without the root token |
| 7 revoke | `vault token revoke -self` with the old root token, deletes `vault-bootstrap-credentials` and `vault-unseal-configure-credentials` | no root token, no key material in the cluster |
| 8 rekey (optional) | `vault operator rekey -target=recovery` to 3 shares / threshold 2 | new keys in the recovery file |

**Recovery keys after a seal migration.** Migrating from Shamir to awskms
converts the existing unseal key shares into recovery key shares: after
step 5 the old unseal key (1 share, threshold 1) IS the recovery key. Step 5
writes it to `ansible/vault-recovery-<cluster>.json` before step 7 deletes
the Secret that held it. One share with threshold 1 is weaker than a fresh
install's 3/2, so rekey it - step 8, or by hand later.

### Rekey the recovery keys

Rekey endpoints are authorized by the current key shares, not by a token,
so this works after the root token is revoked:

```sh
oc exec -n zuno-vault zuno-vault-0 -- \
  vault operator rekey -target=recovery -init -key-shares=3 -key-threshold=2
# note the Nonce, then provide the current recovery share:
oc exec -n zuno-vault zuno-vault-0 -- \
  vault operator rekey -target=recovery -nonce=<nonce> <current recovery key>
```

Store the three new keys like a fresh install's, and destroy the old one.

### After the migration

1. `make d0 install vault` (normal run: configure Job, seeds through
   `ansible-seeder`).
2. `make d0 install cert-manager`, `make d1 install service-mesh`,
   `make d1 install mariadb`: the ClusterIssuers move to https with the
   service-CA `caBundle`. Until then they still point at `http://...:8200`,
   which the TLS listener refuses - issuance (not existing certificates)
   is down for that window.
3. `make d0 install external-secrets`: per-namespace SecretStores over
   https, then sync the applications so every ExternalSecret moves off
   `vault-backend`. The configure Job keeps the old `eso-reader` role until no
   ExternalSecret references `vault-backend` any more, so run
   `make d0 install vault` once more after this item to retire it (see
   "The `eso-reader` role" below).
4. After a week without a rollback, delete the old file data
   (`/vault/data/file-legacy`, a few MB) from a debug pod mounting the PVC,
   and the `vault-pre-kms-raft-*` VolumeSnapshot.

### Rollback

Before step 7 the old root token and unseal key still exist; after step 7
only the recovery file has the (migrated) key.

1. Stop Vault: remove `syncPolicy.automated` from `zuno-vault-d1` (step 2's
   patch) and scale `statefulset/zuno-vault` to 0.
2. Restore the volume: delete PVC `data-zuno-vault-0`, recreate it with the
   same name, storage class and size and
   `dataSource: {kind: VolumeSnapshot, apiGroup: snapshot.storage.k8s.io,
   name: vault-pre-kms-raft-<timestamp>}`. (Faster alternative before step 5
   only: the file data is untouched under `/vault/data/file-legacy`; move it
   back to `/vault/data` from a debug pod and delete `raft/`.)
3. Put the old chart back: check out the pre-WP-223 revision of
   `gitops/charts/vault` (standalone, `storage "file"`, `tls_disable`) as the
   Application's `targetRevision`, or `git revert` the WP-223 commit on that
   branch, and sync.
4. Unseal with the old key (from the Secret if step 7 has not run, else
   from the recovery file - before step 5 it is still a Shamir unseal key;
   the snapshot predates the seal migration in every case).
5. Re-run the old clients' revisions (ClusterIssuers on http) if they were
   already switched.

### Resuming after a failure

The playbook can be resumed: `-e vault_migrate_resume_from=N` (N from 1 to 7) skips the steps before N. The legacy
Secret keeps the unseal key and the root token until step 7, so N cannot be above 7. The snapshot (rollback point) is looked up
as the newest `vault-pre-kms-raft-*`, or given with `-e vault_migrate_snapshot_name=...`. The data comparison after steps 4 to 6 runs only if
`-e vault_migrate_probe_expected=<value>` is given (the value of the probe path before the migration; step 0 of the first run prints it as `probe ... = <value>`).
A failure in step 3 leaves Vault stopped: fix the cause, then resume from 3.

### Key checks before anything is stopped

Step 0 calls `kms:DescribeKey` and then a real `kms:Encrypt` / `kms:Decrypt` round trip, the two operations the `awskms` seal needs.
A policy that allows DescribeKey only is refused here, not by a crash-looping Vault at step 5.

### The `eso-reader` role

The configure Job (step 6, and every `make d0 install vault`) deletes the old `eso-reader` role only when no ExternalSecret still points at the
`vault-backend` store. Right after step 6 all 103 still do, so the role is kept; run `make d0 install vault` again once external-secrets and the
applications have synced, and the role is retired.

### Rekey output

`vault operator rekey -format=json` returns the new shares under `keys_base64`. Step 8 writes the raw output to
`ansible/vault-recovery-<cluster>.rekey-raw.json` (0600) before parsing it, so the shares cannot be lost to a parsing error.

## Restore from a raft snapshot

See `docs/platform/backup-recovery.md`, section Vault: a raft snapshot
restores only into a Vault that can use the same KMS key, and a brand-new
Vault needs `-force` plus the recovery keys of the snapshot's Vault for any
later root-token operation.
