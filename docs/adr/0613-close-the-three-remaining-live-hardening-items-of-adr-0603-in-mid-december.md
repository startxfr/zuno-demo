# ADR-0613: Close the three remaining live hardening items of ADR-0603 (M4, M2, M7) in mid-December

- **Status:** Proposed
- **Target:** v0.17
- **Date:** 2026-11-12
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0603](0603-close-the-medium-severity-security-gaps-found-in-the-2026-11-06-review.md), [ADR-0602](0602-harden-the-platform-trust-boundaries-before-a-customer-runs-it.md), [ADR-0606](0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md), [ADR-0609](0609-rehearse-on-canary-namespaces-of-demo333.md)

## Context

The status table that ADR-0603 gained on 2026-11-12 leaves three findings open on the live cluster, and nothing else
that needs a live window: M2 (database transport), M4 (the Keycloak HTTP listener) and M7 (the internal PKI root).
M7 had no work package. None of the three is a known flaw that someone can exploit today. Each is **hardening in depth**:
it limits what an attacker can do after a first compromise elsewhere (a pod in the cluster, a leaked Vault token), and it
does not stop a first compromise. They are scheduled together, in a distant window, because the demonstration band is
closed and each of them needs its own cluster window with the user's go.

### Findings

| # | Finding | Kind | Evidence |
|---|---|---|---|
| M4 | Keycloak keeps `httpEnabled: true`; the operator's NetworkPolicy admits port 8080 from any source, so tokens and sign-in forms can cross the cluster in clear text | Hardening: removes an unexposed plain-text surface | `gitops/charts/keycloak/templates/keycloak.yaml:46-47`, ADR-0603 M4 |
| M2 | PostgreSQL and MariaDB run with `tls.mode: DISABLE` in the mesh; clients use `sslmode` `require` or `prefer`, which encrypt but do not check who answers | Hardening, the closest to a corrective: a pod that took over the database address would be accepted | `gitops/charts/postgresql/templates/destinationrule-postgres.yaml:59`, `gitops/charts/mariadb/templates/destinationrule-mariadb.yaml:23`, `sslmode` in the aap, dify, mlflow, mlops and kagent charts |
| M7 | The PKI root lives in Vault with a 10-year lifetime, no intermediate and no offline root; the three cert-manager Vault roles share one ServiceAccount, so the key that signs Istio identities is the one that signs application certificates | Hardening in depth: a smaller blast radius if Vault or that ServiceAccount is compromised | `ansible/roles/vault/kustomize/configure/configure.sh:130-134` |

## Decision

**Close M4, M2 and M7 in this order, one work package each, in a window planned for mid-December 2026 (about 14 to 18 December),
with local code and tests first and a separate go from the user for every cluster window.**

1. **M4 first (WP-252).** Decide between two ends: limit port 8080 to its real callers (the in-cluster Jobs and the router),
   or accept it with a documented reason if measurement shows no caller can move to HTTPS. The decision is recorded in the
   work package with the list of callers it measured.
2. **M2 second (WP-253).** Database-native `verify-full` for every client, one database engine at a time, PostgreSQL first.
   Each client moves in its own lot with its own rollback. The mesh `DISABLE` stays: the database terminates TLS itself.
3. **M7 last (WP-254).** Add an intermediate CA under the root (or move the root offline) and give the Istio role its own
   ServiceAccount. It is last because it re-issues certificates for the whole mesh and is the only item without a rehearsal
   in a canary namespace today.
4. **Every window follows the standing rules.** Announced to the other sessions before it starts and closed after; a golden
   path after it; a rollback written before the go is asked for; no secret printed. A canary rehearsal comes first when
   [ADR-0609](0609-rehearse-on-canary-namespaces-of-demo333.md) can express it.
5. **Slippage is allowed, silent drop is not.** If December moves, the work packages keep their state and the date is
   changed in the roadmap with a dated note.

## Alternatives considered

- **Do nothing and accept all three.** Defensible for M4 only, and it is a permitted outcome of WP-252. M2 and M7 stay
  worth doing before a customer runs the platform (ADR-0602 goal).
- **Do them now.** Rejected: the live windows already spent on WP-250, WP-251 and the UnifAI pin leave no slack, and
  ADR-0606 caps work in progress.
- **One work package for all three.** Rejected: the three have no common code, different risks and rollbacks, and need
  separate windows.

## Consequences

- ADR-0603 can reach `Implemented` once the three windows close (M6 and the owner actions are tracked there).
- M2 touches every database client; a client with a wrong CA breaks its application, which the per-client lots contain.
- M7 changes the trust chain: workloads that pin the old root must also trust the new chain during the transition.

## Security considerations

None of the three fixes a vulnerability. They shrink the reach of a first compromise: clear-text tokens inside the cluster
(M4), an impostor database (M2) and a single long-lived signing key shared by every certificate role (M7). The record does
not claim more than that.

## Operational considerations

Three cluster windows, each with the user's go. Estimates: M4 about half a day, M2 two to three days across clients, M7
one to two days with a rehearsal. Operators watch ArgoCD health and the golden path after each, and keep the written
rollback at hand.

## Work packages

[WP-252](../roadmap/work-packages/wp-252-limit-or-accept-the-keycloak-http-listener.md) (M4),
[WP-253](../roadmap/work-packages/wp-253-verify-full-database-transport-for-every-client.md) (M2),
[WP-254](../roadmap/work-packages/wp-254-intermediate-ca-and-separate-istio-service-account.md) (M7).
