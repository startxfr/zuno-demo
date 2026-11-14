# ADR-0603 M9: Vault seeding without a secret on the exec command line (2026-11-12)

The work was done with the user's go, by session zuno-avancement. The window ran from 16:24 to 16:40 UTC and was
announced to zuno-main and zuno-demo.

## The gap

Every Vault write and read of the seeding ran as
`k8s_exec sh -c "VAULT_TOKEN=<token> vault kv put <path> key=<secret> ..."`. The command of a pod exec is part of the
request's URL, so the token and the values reached three places:
- the API server's audit log;
- the process list of the Vault pod;
- the task result on a failure, where `no_log` hid them only once it was set.

## The change

- **`ansible/tasks/vault_cli.yml` (new).** It runs one `vault` command with no secret on its command line:
  1. a private directory is created in the pod (mode 700);
  2. the token, and the payload as a JSON object of strings, are copied into it with `kubernetes.core.k8s_cp`, which
     streams them as a tar archive on the exec's stdin;
  3. the command reads them from there (`@PAYLOAD` stands for the payload file);
  4. the same exec deletes the directory, and an `always` step deletes it again after a failure.
  A `kv get` keeps no stdout unless asked, and a failure prints the vault arguments only.
- **`ansible/tasks/vault_seed_if_missing.yml`**, used by the create-if-missing seeds of every role, does its existence
  check and its seed through the helper.
- **The vault role**:
  - 17 operator-supplied writes, the PKI root read, the cluster-domain write and the provider API keys go through the
    helper;
  - the two "check, then placeholder" loops (operator secrets, LLM providers) now use `vault_seed_if_missing.yml`.
    They stop on a read error other than "no value found", where the old loops seeded a placeholder over it.
- `VAULT_TOKEN={{` occurrences in the role and the helper: 26 before, 0 after.

## Live checks

| UTC | Step | Result |
|---|---|---|
| 16:24 | read-only probe of the helper (scratch playbook) | `kv get` of an existing path rc 0, no stdout kept; of a missing path rc 2; the PKI root read returns the certificate; no private directory left in the pod's `/tmp` |
| 16:25-16:35 | `make d0 install vault` from the session's worktree | exit 0, `ok=728 changed=24 failed=0`; 20 writes through the helper; the string `VAULT_TOKEN=` appears 0 times in the run's log |
| 16:36 | current and previous version of each re-seeded path compared in the pod (only same or differs printed) | 20 paths "same" (the JSON payload stores exactly what `key=value` stored); 3 placeholders untouched (v1); `maas/gateway-api-key` absent, as before |
| 16:38-16:39 | `make demo golden-path` | RESULT PASS, 14 moments, world model as roadmap |

## Still on the command line (follow-up)

- **20 calls in other roles and playbooks**, to move to the helper one role at a time, each with a run of its role:
  - `aap_config` 5, `vault_migrate_kms_raft.yml` 4, `dify` 3, `quay_registry` 2;
  - 1 each in `redis`, `mariadb` and `keycloak` external mode, `postgresql` (`precreate_one_pguser_secret.yml`),
    `openclaw` and `vault/bootstrap_auth.yml`.
- **The vault role's root-token steps** (the one-time bootstrap and the root token revocation) run once in a Vault's
  life and cannot be rehearsed without a new Vault. They keep their `no_log`.
