# WP-177: Finish the MaaS quota delegation

- **State:** Not started
- **ADRs:** [ADR-0570](../../adr/0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md)
- **Depends on:** [WP-157](wp-157-slim-the-ai-gateway-via-maas.md)
- **Related:** [ADR-0511](../../adr/0511-define-okf-quota-policy-enforced-via-kuadrant.md), [ADR-0528](../../adr/0528-rekey-project-binding-quota-and-telemetry-onto-the-zuno-project-id.md), [WP-54](wp-54-quota-policy-and-kuadrant-translation.md)
- **Target:** v0.12
- **Estimated files touched:** ~10 in `zuno-demo` once unblocked (`components/ai-gateway/app/{quota.py,quota_budgets.yaml,main.py}`, their tests, `platform/okf/generate_quota_enforcement.py`, `gitops/charts/connectivity-link`)

> The part of ADR-0570 that WP-157 could not deliver: token ceilings at MaaS for the user, the group and all models together,
> then the removal of the gateway's ledger. It cannot start until Kuadrant counts more than two limits per route.

## Goal

Every token ceiling of the quota policy (user, group, cross-model, and the `evaluation`, `intensive` and `stresstest` classes)
is enforced by Kuadrant `TokenRateLimitPolicy` and proven by live counters, then `app/quota.py` and its budgets leave the
ai-gateway.

## Why it is blocked

The wasm shim completes only the first two limits of a route, by sorted limit name, so the gateway-level `standard-*` pair
never counts next to the controller's subscription limits. Confirmed on 2026-10-25 with a throwaway Gateway, route and policy
(four limits, ten requests: `l1` and `l2` counted, `l3` and `l4` never; renaming `l1` to `z1` moves the pair). Evidence:
[wp-157-inventory.md](../evidence/wp-157-inventory.md) (follow-up of 2026-10-25). No Zuno-side reordering works: putting the
`standard-*` limits first stops the subscription budgets from counting, which was tried and reverted (000f6d75). The user
accepted the missing per-user ceiling on 2026-10-25.

## Steps

1. **Upstream report.** File the issue from
   [kuadrant-token-limits-upstream-report.md](../evidence/kuadrant-token-limits-upstream-report.md), drafted and not filed. Filing is
   the user's decision.
2. **After a fixed Kuadrant.** Re-run the minimal reproduction (all four limits counted), then the live order check on demo333:
   the subscription, group and user counters all move for one persona chat on a route with several subscription limits. Render
   the `evaluation` and `stresstest` limits (`enforceNonStandardClasses`) only if a caller can reach them.
3. **Cross-model total (V8).** A policy whose counter spans routes, or another design; counters are per route today.
4. **Closed class during a Limitador outage (V14).** The MaaS path is fail-open today (about one call in five fails); decide
   whether `closed` needs a gateway-side guard.
5. **Removal, only on proven equivalence.** Remove `app/quota.py`, `quota_budgets.yaml`, `tests/test_quota_budgets.py`, the
   ledger calls and `_render_budgets`.

## Checks never run

| Check | Why |
|---|---|
| V2, V3, V5 | They need an ExternalModel with egress (`MAAS_EXTERNAL_EGRESS_ENABLED=false`); the vendor route defect is open. SaaS providers stay direct (ADR-0570 exception). |
| V6 | Personas no longer reach MaaS (401), so the choice among several subscriptions cannot be exercised with a persona token. |
| V11 | Needs a verified project id; a server-resolved one (ADR-0528) is not implemented. |
| Lightspeed counter | Not exercised in real use since the Limitador restart. |

## Side items

- A dedicated Keycloak client for stress and evaluation scripts: `zuno-evaluations` is in `TRUSTED_PLATFORM_CLIENTS`, which
  weakens the WP-146 header protection for tokens of that client.
- Existing Limitador counters keep the `max_value` they were created with, so a limit change reaches them only when their
  window ends; plan any limit change around that.

## Acceptance

The four limits of a route are all counted on demo333 with the fixed Kuadrant, a breach of each ceiling returns 429, and the
ai-gateway image holds no `quota.py`; or the user drops the removal and ADR-0570 is amended to say so.
