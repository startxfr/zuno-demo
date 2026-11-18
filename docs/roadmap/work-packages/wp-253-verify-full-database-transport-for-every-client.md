# WP-253: Verify the database server certificate in every client with `verify-full` (ADR-0603 M2)

- **State:** Not started (planned window: about 15 to 17 December 2026)
- **ADRs:** [ADR-0613](../../adr/0613-close-the-three-remaining-live-hardening-items-of-adr-0603-in-mid-december.md),
  [ADR-0603](../../adr/0603-close-the-medium-severity-security-gaps-found-in-the-2026-11-06-review.md) (M2)
- **Depends on:** none; [WP-252](wp-252-limit-or-accept-the-keycloak-http-listener.md) goes first by the ADR's order
- **Related:** [WP-254](wp-254-intermediate-ca-and-separate-istio-service-account.md) (the CA chain the clients will trust)
- **Target:** v0.17
- **Estimated files touched:** ~12: the postgresql and mariadb charts, the `sslmode` values of the client charts (aap, dify,
  mlflow, mlops, kagent, quay_registry role), the CA bundle wiring, the mlops component default, this brief

> Execute this brief as a standalone task from the repository root. Code and tests are local first; every cluster action needs the
> user's go, outside a freeze, with a golden path after it. One client per lot, each with its rollback.

## Why

PostgreSQL and MariaDB run with the mesh in `DISABLE` mode, and the clients use `sslmode` `require` or `prefer`. Those encrypt the
connection but accept any certificate, so a pod that took over the database address would be trusted. `verify-full` also checks the
CA and the host name. This is **hardening**, the closest of the three items to a corrective: it closes a real, low-probability
impersonation gap. Memory notes to read first: the PGO CA bundle must stay additive; PGO does not recreate a dropped database.

## Goal

Every client of the two engines connects with `verify-full` (PostgreSQL) or the MariaDB equivalent (`ssl-verify-server-cert`), against
the platform CA, and a connection with a wrong CA fails.

## Design

1. **Inventory (read-only):** every client, its `sslmode` today and where it reads the CA from.
2. **Server side:** confirm each server certificate carries the service host names the clients use.
3. **Client side, one lot each:** set the mode, mount the CA bundle (additive), restart, check.

| Option | Verdict |
|---|---|
| **A. `verify-full` per client, PostgreSQL first (recommended)** | Real server authentication, contained per client |
| B. Mesh mTLS to the database instead | Rejected earlier: database sniffing and PGO ports make it fragile (see memory notes on mesh port exclusions) |
| C. Keep `require` and accept | Leaves the impersonation gap open |

## Lots

| Lot | Content | Live effect |
|---|---|---|
| 1 | Inventory and server-certificate host-name check | none |
| 2 | Code and chart changes for the clients, with render tests | none until applied |
| 3 | PostgreSQL clients, one per window step: apply, restart, probe, golden path | each client restarts once |
| 4 | MariaDB clients, same pattern | each client restarts once |

## Proof

- For each client: a connection with the right CA works; the same pod with a wrong CA is refused.
- Golden path 13/13 after the last lot.

## Rollback

Per client: set `sslmode` back to its previous value and re-run the install. No data is touched.

## Out of scope

- The mesh `DISABLE` stays. Changing the CA chain is [WP-254](wp-254-intermediate-ca-and-separate-istio-service-account.md).
