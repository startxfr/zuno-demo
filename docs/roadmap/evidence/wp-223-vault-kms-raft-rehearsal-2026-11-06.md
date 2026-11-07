# WP-223: Vault migration rehearsal (2026-11-06)

`platform/vault/rehearsal/rehearse_kms_raft_migration.sh` replays the Vault commands of
`ansible/playbooks/vault_migrate_kms_raft.yml` on a local podman Vault 1.17.2. The run used the real AWS KMS key
(eu-central-1, symmetric, `Enabled`) and the dedicated IAM user `zuno-vault-unseal`. No cluster was involved.

## Output

```text

=== 0. legacy Vault: file storage, Shamir 1/1 (today's install.yml)
seeded 3 keys; sealed=False storage=file

=== 2-3. stop, move file entries to file-legacy/, vault operator migrate file -> raft
Success! All of the keys have been migrated.

=== 4. start on raft (still Shamir), unseal, verify data
sealed=False storage=raft
secret-1secret-2secret-3
=== 5. seal migration Shamir -> awskms (unseal -migrate)
sealed=False type=awskms recovery_seal=True

=== 6. restart: must unseal by itself through KMS
sealed=False type=awskms
secret-1secret-2secret-3
=== 7. revoke the root token
root token revoked (403 as expected)

=== 8. generate-root with the recovery key (the former unseal key), then rekey recovery to 3/2
secret-1rekey -> 3 recovery keys

REHEARSAL OK
```

## What it proves

- **Storage migration:** `vault operator migrate` copies a Shamir-sealed `file` Vault into raft once the file
  entries are moved to `file-legacy/`. The data reads back after an unseal with the old key.
- **Seal migration:** `unseal -migrate` with the old Shamir key turns the seal into `awskms`
  (`recovery_seal=True`).
- **Auto-unseal:** after a restart the server unseals alone through KMS. This is the gap that left demo333 sealed
  after every pod restart.
- **Root token and recovery:**
  - The root token is revoked.
  - The former unseal key works as the recovery key for `generate-root`.
  - `rekey -target=recovery` then gives 3 keys, threshold 2.

## Findings fed back into the repo

- **Wrong KMS key or credentials stop Vault from starting.** A first run used deliberately wrong credentials, and the
  server refused to start: "error fetching AWS KMS wrapping key information". Step 0 of the playbook now runs a real
  `kms:DescribeKey` with the IAM credentials before anything is stopped.
- **The migrate step must run as the Vault user.** Run as root, the raft database it creates is not writable by Vault.
  In the cluster the Job runs under the pod's own user, so this only matters for local runs.

## Not covered

- TLS and Kubernetes auth: there is no Kubernetes API locally. These are covered by chart renders and by the rollout
  checks of the WP-223 brief.
