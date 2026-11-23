# WP-331: Show Vault through its web UI in the vault-pki demo

- **State:** Repo work in review (2026-11-23: the role, the Route switch and the token script; the page, its steps and
  its GIF follow once the Route and the token work on demo333)
- **ADRs:** [ADR-0628](../../adr/0628-publish-the-vault-ui-on-a-route-entered-with-a-read-only-demo-token.md)
- **Depends on:** [WP-223](wp-223-secrets-and-identity-hardening-vault-eso-passwords-keycloak.md) (the Vault identities
  and the Route switch it built)
- **Related:** [WP-287](wp-287-record-terminal-demos-as-real-sessions-checked-as-text.md) (the GIF takes)
- **Target:** v0.18
- **Estimated files touched:** ~20: `ansible/roles/vault/kustomize/configure/` (policy, `configure.sh`, kustomization),
  `ansible/roles/vault/tasks/run_configure_job.yml`, `ansible/inventories/demo333/cluster.yml`,
  `platform/vault/demo_token.sh` and its tests, `docs/demo/scenarios/foundation/vault-pki.md`,
  `ansible/demos/vault-pki/`, `evaluations/browser/walkthroughs/vault-pki.mjs`, the CI

## Goal

The vault-pki demo shows how Zuno uses Vault in Vault's own web UI: secret names and versions and who reads them,
the Transit keys, the PKI root and roles, the auth methods and policies. The presenter mints a read-only, 30-minute
token in the terminal, then works in the browser only. No secret value can reach the screen or the GIF.

## Work

1. The policy and role `demo-reader`, the ServiceAccount `vault-demo-reader` (no RBAC), in the configure Job.
2. The chart's reencrypt Route on demo333 (`zuno_vault_route_enabled: true`, no allow-list), then the hand-made Route
   `vault` deleted.
3. `platform/vault/demo_token.sh`: `oc create token`, Vault login inside the pod with the JWT on stdin, token to the
   clipboard; `--print` to a pipe only.
4. Tests: `platform/vault/tests/test_demo_reader_policy.py`, `platform/vault/tests/test_demo_token.py`, in the CI.
5. The page: the 5-minute version becomes the UI tour after the token; the terminal rows move to the 15-minute version.
   Steps, `demo.yml` (`record: {kind: assembled}`), `gif.yml`, the walkthrough `vault-pki.mjs`.
6. The GIF, assembled from a terminal still and the browser take, after the owner's "go vault-pki".

## Acceptance

- The two tests and `check_secret_access.py` pass; `helm template gitops/charts/vault --set route.enabled=true` renders
  one reencrypt Route.
- On demo333, after the owner's go and `make d0 install vault`: Route `zuno-vault` answers
  `https://vault.apps.demo333.startx.fr/ui/` with a trusted certificate; the script's token signs in; every page of the
  tour renders; a `zuno/data` read and any write are denied; the ExternalSecrets stay `SecretSynced`.
- `consistency.py` and the catalogue tests pass; the GIF is 40-60 s, under 8 MB, with no token, value or password in any
  frame.

## Out of scope

An IP allow-list (possible at any time), another cluster, and the Raft and audit pages of the UI (they need `sudo`).
