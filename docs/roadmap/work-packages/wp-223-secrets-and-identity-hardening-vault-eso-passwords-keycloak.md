# WP-223: Secrets and identity hardening: Vault, External Secrets, passwords, Keycloak (delivers ADR-0602)

- **State:** Operator pending (2026-11-06). Repo work complete and committed locally on branch
  `wp-223-secrets-identity` (based on the WP-222 commit), not pushed; the migration was rehearsed end to end with the
  real KMS key. The demo333 migration waits for the push and the user's go.
- **ADRs:** ADR-0602, ADR-0603
- **Depends on:** WP-222
- **Blocks:** WP-227
- **Estimated files touched:** ~200

> Execute this brief as a standalone task from the repository root. Every cluster action needs the user's go.

## Goal

Make Vault a real root of trust (C1), let each namespace read only its own secrets (C2), end the shared infrastructure
password outside the demo profile (C5), and harden the realm (M5, M6, M8).

## ADR references

ADR-0602 clauses 1 to 3; ADR-0603 clause 2 (M5 to M9).

## Decisions taken with the user (2026-11-06)

| Topic | Decision |
|---|---|
| Unseal | AWS KMS. The operator creates the key and a dedicated IAM user (`kms:Encrypt`, `kms:Decrypt`, `kms:DescribeKey` on that key only) and puts four variables in `ansible/confidential.yml`. |
| Existing Vault | Migrated in place by a script: CSI snapshot, then `file` to `raft`, then Shamir to awskms. Rollback is the snapshot. |
| Secret reach | One `SecretStore` per namespace, generated from one table; the `vault-backend` ClusterSecretStore is removed. |
| Root token | Replaced by Kubernetes-auth roles with one-hour tokens. Revoked after bootstrap. Recovery keys go to the operator outside the cluster. |
| Profile | `zuno_security_profile: demo\|hardened`. **demo333 stays `demo`.** |
| Keycloak | Temporary brute-force protection in both profiles. Password policy, a one-hour idle session and OTP for `zuno-admin` in hardened only. OTP is not put on `zuno-automation`, because a required action would block the Jobs' password login. **The password grant stays on `openshift` and `aap`.** |
| Vault UI / htpasswd | The UI Route is off by default (IP allow-list available as a value). The htpasswd identity provider is kept as the documented break-glass login. |

## Live finding confirmed before the work

On 2026-11-06, `oc auth can-i create externalsecrets -n zuno-ai-run` answered `yes` for both `ocp-ai-dev` and
`ocp-ai-ops`. The single `vault-backend` store, which was also `ReadWrite`, therefore let either group read, and through
a PushSecret write, any key of `zuno/*`.

## Repo changes

1. **Vault chart (`gitops/charts/vault`).**
   - Storage is `raft` at `/vault/data/raft` (HA mode, 1 replica, `retry_join` over https per replica).
   - `seal "awskms"` comes from `vault.seal.type` and `vault.kms.{region,keyId}`. The chart refuses to render without
     a key, which also keeps ArgoCD from applying it to a Vault that has not been migrated.
   - The listener uses TLS with the service-CA Secret `vault-tls`. The in-pod CLI gets `VAULT_CACERT` and
     `VAULT_TLS_SERVER_NAME`.
   - AWS credentials come from Secret `vault-aws-kms`, which Ansible creates.
   - The Route is off by default; when enabled it is reencrypt with an optional `ip_whitelist`.
   - A raft-snapshot CronJob uses its own Kubernetes-auth role.
2. **Vault role.**
   - `operator init` gives recovery keys 3 of 2. They are written once to `ansible/vault-recovery-<cluster>.json`
     (gitignored, mode 600).
   - The root token reaches `bootstrap_auth.yml` over exec only, creates `vault-configurator`, and is revoked once the
     configure Job succeeds.
   - New `kustomize/configure/`: `configure.sh` plus policies. It creates the `vault-configurator`, `ansible-seeder`,
     `raft-snapshot` and `ns-<namespace>` roles, and removes `eso-reader` and stale `ns-*` roles.
   - `install.yml` stops if the old bootstrap Secret still exists, because a pre-WP-223 Vault must go through the
     migration.
3. **No more root-token reads.** New `ansible/tasks/vault_login.yml`: a one-shot ServiceAccount token for
   `ansible-seeder`, used for one login and deleted in an `always:` block. kubernetes.core 6.2 cannot call
   TokenRequest. Every former root-token reader now uses it: `vault_seed_if_missing.yml`, aap_config, dify, kagent,
   open_webui, openclaw, mariadb, postgresql. The AAP Role that could read every Secret in `zuno-vault` is deleted.
4. **Clients over https.**
   - The three cert-manager ClusterIssuers use https with `caBundle`, which Ansible fills
     (`ansible/tasks/resolve_vault_ca_bundle.yml`).
   - `sign_in_cluster.py` uses https and `VAULT_CACERT`.
   - The PKI AIA and CRL URLs are https.
5. **Migration.** `ansible/playbooks/vault_migrate_kms_raft.yml`, steps 0 to 8, pauses before each step. Runbook
   `docs/platform/vault-kms-raft-migration.md`, with the IAM policy and the KMS steps. The Vault section of
   `docs/platform/backup-recovery.md` is rewritten for raft snapshots, the KMS key and the recovery keys.
6. **Per-namespace SecretStores.**
   - `platform/vault/secret-access.yaml` holds 19 namespaces, 95 grants and 67 keys, with no prefix grants.
   - Most stores (16) are rendered by `gitops/charts/external-secrets`. Each store is a ServiceAccount `vault-reader`
     plus a SecretStore `vault` (role `ns-<namespace>`, service-CA `caProvider`).
   - `cert-manager` and the `zuno-claw-*` namespaces get their store from their own chart, because those namespaces are
     created later.
   - All 103 ExternalSecrets point to `{kind: SecretStore, name: vault}`.
   - The lightspeed key no longer has a double `zuno/` prefix; serviceIdentity mode could never have synced before.
   - New check `platform/vault/check_secret_access.py`, with 16 tests, is wired into `lint.yml`.
7. **Passwords.**
   - `zuno_security_profile` (asserted by `ansible/tasks/assert_security_profile.yml`; hardened also requires a persona
     password of 12+ characters with a digit).
   - In hardened, the 23 infrastructure variables are `undef()`, so each consumer's random default applies. Defaults
     were added where missing: keycloak console and automation, dify, openclaw.
   - The md5 fallback fails in hardened.
   - `zuno_admin_token`, `zuno_admin_vault_token` and `zuno_admin_mcp_gateway_token` are removed, so the mcp-gateway
     token is random. Live values are unchanged, because seeding only writes missing keys.
   - The vault and keycloak roles load the per-cluster variables.
8. **Keycloak.**
   - The chart value `securityProfile` drives a `realm-settings.json` that the reconcile Job applies with `kcadm
     update realms/zuno -f … -m`.
   - The brute-force keys are also added to `realm-zuno.json`.
   - In hardened only: OTP for `zuno-admin`, set while it has no OTP credential.
   - A test guards `directAccessGrantsEnabled` on `openshift` and `aap`.

9. `.gitleaks.toml`: the default rules plus one documented false positive. The default rule
   `kubernetes-secret-yaml` matches `kind: SecretStore` up to the `remoteRef` key, so all 31 ExternalSecrets touched
   here would have failed the WP-222 secret scan. A real `kind: Secret` with data is still flagged (tested).

## Verification (2026-11-06)

- **Checks:**
  - `check_docs.py`: PASS.
  - `check_secret_access.py`: PASS (103 ExternalSecrets, 19 stores, 586 rule checks).
  - `check_workload_hardening.py`: PASS.
- **Tests:**
  - `test_password_scheme.py`: 18/18.
  - pytest `platform/keycloak/tests` + `platform/vault/tests`: 33 passed.
- **Helm:** `helm template` passes for vault (with a key), cert-manager, mariadb, service-mesh, aap-config,
  external-secrets, openclaw and keycloak in both profiles. 76 renders of the charts carrying ExternalSecrets pass.
- **Ansible:** `--syntax-check` OK on `vault_migrate_kms_raft.yml`, `day0_install.yml` and `day0_check.yml`. Outside
  the init, the one-time bootstrap and the migration playbook, nothing reads `root_token`.
- **Repo against live** (95 live ExternalSecrets, 103 in the repo): nothing is live without being in the repo, and the
  shared ones read the same keys. The 8 that exist only in the repo belong to components that are off on demo333.
- **Rehearsal: passed** with the real KMS key (eu-central-1) and the `zuno-vault-unseal` IAM user, local podman
  Vault 1.17.2, no cluster: file to raft, Shamir to awskms, auto-unseal after restart, root revoked, `generate-root`
  with the recovery key, recovery rekeyed to 3/2
  ([evidence](../evidence/wp-223-vault-kms-raft-rehearsal-2026-11-06.md), script
  `platform/vault/rehearsal/rehearse_kms_raft_migration.sh`). It caught one gap: a wrong KMS key or credential stops
  Vault from starting, so playbook step 0 now runs a real `kms:DescribeKey` before stopping anything.

## Rollout (needs the user's go and the push)

1. Run `ansible-playbook ansible/playbooks/vault_migrate_kms_raft.yml`, step by step: snapshot, file to raft, Shamir to
   awskms, roles, root-token revocation, then `rekey -target=recovery` to 3 of 2.
2. Re-run the cert-manager, service-mesh and mariadb roles. Until then the ClusterIssuers still point at http.
3. Sync external-secrets so the stores become Ready, then the applications, and check every ExternalSecret is `Ready`.
   `vault-backend` is pruned. The existing Secrets are kept until each application syncs.
4. Restart the Vault pod and confirm it unseals by itself.
5. Back-out: restore the CSI snapshot and the previous chart values.

## Not done here

- Who may create an `ExternalSecret` is unchanged. The blast radius is now one namespace's keys, not the whole tree.
- The password grant on `openshift` and `aap` is kept by decision.
