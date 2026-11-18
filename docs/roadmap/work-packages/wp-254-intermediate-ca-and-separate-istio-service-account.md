# WP-254: Add an intermediate CA and a separate ServiceAccount for the Istio role (ADR-0603 M7)

- **State:** Not started (planned window: about 17 to 18 December 2026; no canary rehearsal exists yet)
- **ADRs:** [ADR-0613](../../adr/0613-close-the-three-remaining-live-hardening-items-of-adr-0603-in-mid-december.md),
  [ADR-0603](../../adr/0603-close-the-medium-severity-security-gaps-found-in-the-2026-11-06-review.md) (M7)
- **Depends on:** [WP-253](wp-253-verify-full-database-transport-for-every-client.md) (clients first, so they trust the final chain once)
- **Related:** [ADR-0609](../../adr/0609-rehearse-on-canary-namespaces-of-demo333.md)
- **Target:** v0.17
- **Estimated files touched:** ~8: `ansible/roles/vault/kustomize/configure/configure.sh`, the cert_manager role and issuers, the
  Vault policy and role for the Istio issuer, the istio-csr wiring, this brief

> Execute this brief as a standalone task from the repository root. Code and tests are local first; every cluster action needs the
> user's go, outside a freeze, with a golden path after it. Rehearse first.

## Why

The internal PKI root is generated in Vault with a 10-year lifetime. There is no intermediate and no offline root, and the three
cert-manager Vault roles share one ServiceAccount, so whoever holds that identity can sign mesh identities as well as application
certificates. This is **hardening in depth**: it shrinks the damage of a Vault or ServiceAccount compromise. It fixes nothing that
is being exploited. It is the largest item because every workload certificate depends on the chain.

## Goal

The root signs only an intermediate. Issuance goes through the intermediate. The Istio issuer role has its own ServiceAccount and
policy. Workloads trust old and new chains during the transition and the old chain is removed after one certificate lifetime.

## Design

| Option | Verdict |
|---|---|
| **A. Intermediate in Vault `pki_int`, root kept in Vault but used only to sign it (recommended)** | Smallest change, meets the finding, rehearsable |
| B. Offline root, intermediate imported | Stronger, but needs a key ceremony the project does not have |
| C. Keep as is and accept | Leaves one key signing everything |

Steps: create `pki_int`, sign its CSR with the root, point the ClusterIssuers at it, split the ServiceAccounts and Vault roles,
publish the chain, roll certificates by their normal renewal (max_ttl 720 h), then retire the old issuance path.

## Lots

| Lot | Content | Live effect |
|---|---|---|
| 1 | Brief of the rotation, trust-overlap plan and rollback; a rehearsal on a canary namespace if the issuers allow one | none |
| 2 | `configure.sh` and issuer changes, tests that render and lint them | none until applied |
| 3 | Window: create the intermediate, switch the ClusterIssuers, split the ServiceAccounts, golden path | new certificates come from the intermediate |
| 4 | After one renewal cycle: retire the root as a direct issuer, check no leaf chains to it directly | none |

## Proof

- A new leaf certificate chains leaf, intermediate, root. The Istio role cannot sign application certificates and the reverse.
- Mesh mTLS, ArgoCD health and the golden path (13/13) hold during the overlap.

## Rollback

Point the ClusterIssuers back at the root path (kept until lot 4); the previous ServiceAccount binding is restored from git.

## Out of scope

- An offline root or hardware key (option B), and Vault auto-unseal changes.
