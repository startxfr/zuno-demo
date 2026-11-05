# WP-219: Run the ADR-0570 checks once their blockers clear

- **State:** Closed — deferred (2026-11-05: every check is blocked; resume when a blocker below clears)
- **ADRs:** [ADR-0570](../../adr/0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md)
- **Depends on:** [WP-177](wp-177-finish-the-maas-quota-delegation.md)
- **Related:** [WP-157](wp-157-slim-the-ai-gateway-via-maas.md), [ADR-0563](../../adr/0563-forward-caller-identity-and-zuno-context-headers-from-unifai.md)
- **Target:** v0.11
- **Estimated files touched:** ~3: an evidence file, WP-177 and the ADR-0570 closure note

> Why: ADR-0570 stays `Partially implemented` partly because five of its live checks were never run. This WP keeps them in the tracker with the exact blocker of each, so they are not forgotten and not pretended runnable.

## Goal

Run each check below as soon as its blocker clears, record the result, and let ADR-0570 move to `Implemented` (or be amended to accept the ledger as the permanent design).

## The checks and what each waits for

| Check | Waits for |
|---|---|
| V2, V3, V5 | A SaaS ExternalModel with egress through MaaS (`MAAS_EXTERNAL_EGRESS_ENABLED`), which needs the vendor route defect fixed. SaaS providers stay direct, with their keys, until then (ADR-0570's named exception). |
| V6 | A way for a persona token to reach MaaS, or a service token that stands in for it, so the choice among several subscriptions can be exercised. Personas get a 401 from MaaS today. |
| V11 | A project id verified server-side (ADR-0528). ADR-0563 records it as not implemented, and the ai-gateway drops the project dimension for untrusted callers. It needs a new decision first. |

Also tied to the same ADR (WP-177 step 5): once Kuadrant writes all limit families, re-run the minimal reproduction and the probe, then V8 (cross-model total) and V14 (closed class during a Limitador outage), and only on proven equivalence remove `app/quota.py`, `quota_budgets.yaml` and the ledger calls. On 2026-11-05 the gateway-level `TokenRateLimitPolicy` was switched off on demo333 because Kuadrant could not write its wasm config (etcd "request is too large"); the quota ledger of the ai-gateway is what enforces quotas meanwhile.

## Steps

1. When a blocker clears, run the matching check from WP-157's verification list and write the result to an evidence file.
2. Update WP-177's "Checks never run" table.
3. When all are run or retired, amend ADR-0570's closure state and move its status.

## Acceptance

- Each of V2, V3, V5, V6 and V11 has a recorded result or a recorded decision to retire it.
