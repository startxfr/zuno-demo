# WP-252: Limit the Keycloak HTTP listener to its callers, or accept it with a reason (ADR-0603 M4)

- **State:** Not started (planned window: about 14 December 2026)
- **ADRs:** [ADR-0613](../../adr/0613-close-the-three-remaining-live-hardening-items-of-adr-0603-in-mid-december.md),
  [ADR-0603](../../adr/0603-close-the-medium-severity-security-gaps-found-in-the-2026-11-06-review.md) (M4)
- **Depends on:** none
- **Related:** [WP-253](wp-253-verify-full-database-transport-for-every-client.md), [WP-254](wp-254-intermediate-ca-and-separate-istio-service-account.md)
- **Target:** v0.17
- **Estimated files touched:** ~4: `gitops/charts/keycloak/templates/keycloak.yaml`, a NetworkPolicy template in the same chart,
  the chart values, this brief

> Execute this brief as a standalone task from the repository root. Code and tests are local first; every cluster action needs the
> user's go, outside a freeze, with a golden path after it.

## Why

The Keycloak custom resource keeps `httpEnabled: true`, and the operator's NetworkPolicy admits port 8080 from any source. Any pod
that can reach the service can read or replay what crosses that port in clear text. The port is not exposed outside the cluster.
This is **hardening**, not a fix for a known flaw: it removes a plain-text surface that only matters after a first compromise.

## Goal

Port 8080 is either reachable only by a measured list of callers, or kept with a written reason and the list in this brief.

## Design

1. **Measure first (read-only).** List who connects to 8080 and why: in-cluster Jobs (`client-reconcile`, `eval-personas`), the
   OpenShift router, the mesh health probes, tools using the in-cluster issuer (see memory note "Keycloak in-cluster http issuer").
2. **Decide.**

| Option | Verdict |
|---|---|
| **A. NetworkPolicy limits 8080 to the measured callers (recommended if every caller is known)** | Keeps the in-cluster issuer working, removes the open door |
| B. Turn `httpEnabled` off and move every caller to HTTPS | Cleanest, but the token `iss` changes for http callers and breaks verifiers that pin it |
| C. Accept, with this brief as the reason | Allowed outcome if the measure shows callers that cannot move; record them |

## Lots

| Lot | Content | Live effect |
|---|---|---|
| 1 | Read-only measurement of the callers of 8080, and the decision recorded here | none |
| 2 | The NetworkPolicy (or the acceptance text) in the chart, with a test that renders it | none until applied |
| 3 | `make d2 install` of the keycloak chart in a window, golden path, sign-in with `zuno-admin` | Keycloak NetworkPolicy changes; no restart expected |

## Proof

- A pod outside the list gets a refused connection on 8080 and still reaches 8443.
- The reconcile Job, the router and the golden path still work (13/13).

## Rollback

Remove the NetworkPolicy template and re-run the install; ArgoCD restores the operator's default policy.

## Out of scope

- Moving the in-cluster issuer to HTTPS (a separate decision, option B).
- The `keycloak-admin` Secret leftover of the external mode.
