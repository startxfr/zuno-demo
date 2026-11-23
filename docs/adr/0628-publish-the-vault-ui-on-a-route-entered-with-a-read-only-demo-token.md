# ADR-0628: Publish the Vault UI on a Route, entered with a read-only demo token

- **Status:** Proposed
- **Target:** v0.18
- **Date:** 2026-11-23
- **Decision owners:** Zuno Demo architecture team, platform owner
- **Related:** [ADR-0602](0602-harden-the-platform-trust-boundaries-before-a-customer-runs-it.md) clause 1 (the UI Route
  off), [ADR-0603](0603-close-the-medium-severity-security-gaps-found-in-the-2026-11-06-review.md) M8 (the public Vault
  UI), [ADR-0618](0618-give-every-catalogue-scenario-a-gif-with-real-terminal-sessions-checked-as-text-first.md) (the GIF
  takes), [WP-223](../roadmap/work-packages/wp-223-secrets-and-identity-hardening-vault-eso-passwords-keycloak.md)

## Context

On 2026-11-23, the day before the demonstration of 2026-11-24, the platform owner asked that the Vault and PKI demo show
how Zuno uses Vault through Vault's own web UI, in the live demo and in its GIF. The token is minted on the presenter's
workstation in Bash, because a web-only demo cannot mint one; everything after that is web.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | ADR-0602 clause 1 and ADR-0603 M8 turned the Vault UI Route off by default. The chart still renders a reencrypt Route when `route.enabled` is true, with an optional IP allow-list. | `gitops/charts/vault/templates/route.yaml`, `ansible/roles/vault/tasks/apply_vault_app.yml` |
| F2 | On demo333 a passthrough Route `vault` was created by hand in the console on 2026-11-17 and kept by the owner's decision of 2026-11-20. Argo CD does not track it, and the browser shows a certificate warning (the service CA). | `oc get route -n zuno-vault`, managedFields manager "Mozilla" |
| F3 | No Vault identity fits a public screen: every human-usable role can read secret values or change Vault. | `ansible/roles/vault/kustomize/configure/configure.sh` |
| F4 | Some UI pages need `sudo` (`sys/audit`, the Raft configuration). | Vault API documentation |

## Decision

**The chart publishes the Vault UI on demo333, and the presenter enters it with a 30-minute token that can read names
and settings but no secret value.**

1. **The Route belongs to the chart.** `zuno_vault_route_enabled: true` in `ansible/inventories/demo333/cluster.yml`
   renders the chart's Route `zuno-vault`: reencrypt, host `vault.<apps domain>`, served with the router's Let's Encrypt
   wildcard. It is permanent and has no IP allow-list (owner's decision, 2026-11-23). It replaces the hand-made Route
   `vault`, which is deleted once the chart's Route answers. The chart default stays off for every other cluster.
2. **A read-only demo identity.** The configure Job writes the policy `demo-reader`
   (`ansible/roles/vault/kustomize/configure/vault-demo-reader.hcl`) and the Kubernetes auth role `demo-reader`, bound to
   the ServiceAccount `vault-demo-reader` in `zuno-vault` (no Kubernetes RBAC), with `ttl` and `max_ttl` of 30 minutes.
   The policy grants `read` and `list` only, on: KV metadata (`zuno/metadata`, names and versions, never `zuno/data`),
   the mounts and auth methods, the ACL policies, the Transit key list and public keys (never sign, encrypt or export),
   the PKI root certificate and roles, and the Kubernetes auth roles. No `sudo`: the audit device and the backups are
   shown from the terminal.
3. **The token never reaches a screen.** `platform/vault/demo_token.sh` mints it from `oc create token`, logs in inside
   the Vault pod with the JWT on stdin, and copies the Vault token to the clipboard; it prints only the role, the
   policies and the TTL. `--print` writes it to a pipe only, for the GIF's browser take, which types it into the masked
   token field.
4. **Checked as text.** `platform/vault/tests/test_demo_reader_policy.py` fails the build if the policy gains a write
   capability, `sudo`, a `zuno/data` path or a Transit operation, or if the role lives longer than 30 minutes.
   `platform/vault/tests/test_demo_token.py` checks that the token goes only to the clipboard or a pipe.
5. **The GIF is assembled** (ADR-0618 update of 2026-11-17): a terminal still of the script's output and the browser take
   of the UI tour, with every image reviewed before the owner's "go vault-pki".

This decision supersedes the "UI Route off" part of ADR-0602 clause 1 and of ADR-0603 M8 for demo333 only. The
htpasswd break-glass login of M8 is unchanged.

## Consequences

- **A public Vault login page, permanently.** Anyone who reaches `vault.apps.demo333.startx.fr` sees Vault's sign-in.
  Access still needs a Vault token or a Kubernetes identity; the demo token reads no value and expires in 30 minutes.
  An IP allow-list (`zuno_vault_route_ip_whitelist`) can be set again at any time.
- **The certificate warning goes away**: the Route is reencrypt with the router's trusted certificate.
- **`make d0 install vault` applies it**: the Route through the Application values, the role through the configure Job.
  The seeding it re-runs writes only missing paths (ADR-0345).
- **The UI tour depends on the policy.** A page that needs another path is added to the policy and to its test, never
  with `sudo` or a `zuno/data` path.

Work: [WP-331](../roadmap/work-packages/wp-331-show-vault-through-its-web-ui-in-the-vault-pki-demo.md).
