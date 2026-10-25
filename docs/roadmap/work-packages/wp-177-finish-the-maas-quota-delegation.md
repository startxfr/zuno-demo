# WP-177: Finish the MaaS quota delegation

- **State:** Done (2026-10-25)
- **ADRs:** [ADR-0570](../../adr/0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md)
- **Depends on:** [WP-157](wp-157-slim-the-ai-gateway-via-maas.md)
- **Related:** [ADR-0511](../../adr/0511-define-okf-quota-policy-enforced-via-kuadrant.md), [ADR-0528](../../adr/0528-rekey-project-binding-quota-and-telemetry-onto-the-zuno-project-id.md), [WP-54](wp-54-quota-policy-and-kuadrant-translation.md)
- **Target:** v0.12
- **Estimated files touched:** ~9 in `zuno-demo` (`components/ai-gateway/app/quota.py` and its test, `gitops/charts/ai-gateway`, `ansible/roles/llm`, `ansible/clusters/demo333.yml`, `platform/testing/quota_counters_probe.py` and its test, docs)

> Decision of 2026-10-25 (user): no upstream Kuadrant issue for now and no fix expected soon, so the platform works with the
> limitation. The gateway's ledger (`app/quota.py`) stays the guard of the user, group, cross-model and non-standard-class
> ceilings; this WP makes that guard durable and keeps the limitation observable. Removing the ledger is deferred, not planned.

## Goal

Operate token quotas with the Kuadrant two-limit ceiling: per-subscription budgets at MaaS, every other ceiling in the ai-gateway,
the ledger no longer reset by a restart, and a repeatable check that tells whether the ceiling is still there.

## Why the ledger stays

The wasm shim completes only the first two limits of a route, by sorted limit name, so the gateway-level `standard-group` and
`standard-user` limits never count next to the controller's subscription limits. Confirmed on 2026-10-25 with a throwaway Gateway,
route and policy (four limits, ten requests: `l1` and `l2` counted, `l3` and `l4` never; renaming `l1` to `z1` moves the pair).
Evidence: [wp-157-inventory.md](../evidence/wp-157-inventory.md) (follow-up of 2026-10-25). No Zuno-side reordering works:
putting the `standard-*` limits first stops the subscription budgets from counting, which was tried and reverted (000f6d75).
The user accepted the missing per-user ceiling at MaaS on 2026-10-25. The upstream report stays drafted and not filed
([kuadrant-token-limits-upstream-report.md](../evidence/kuadrant-token-limits-upstream-report.md)).

## Steps

1. **Counters probe (repo, done in review).** `platform/testing/quota_counters_probe.py` reads Limitador's counters for one route
   scope, sends one short persona chat through the ai-gateway, reads again and says which family moved (`subscription`, `group`,
   `user`). Exit 0 when the moved set equals the expectation (today: `subscription` only), 1 with an `IMPROVED` line when more
   moved (an upstream fix or a policy change), 2 when it could not run. Run it after any Kuadrant or policy upgrade.
2. **Durable ledger (repo, done in review).** `QUOTA_LEDGER_STORE=redis` (chart value `quotaLedger.store`, cluster variable
   `zuno_ai_gateway_quota_ledger_store`, default `memory`) also writes every increment to the platform Redis
   (`zuno:quota:<class>:<dimension>:<key>:<bucket>`, expiry two windows) and reads the larger of the local and Redis value, so a
   restart or a second replica keeps the budgets. Redis is best effort: a fault is logged once, Redis is skipped for 5 s, and the
   local counters alone apply; no request fails because of it.
3. **Live proof on demo333 (done 2026-10-25, user go).** Build the image from the merged commit, set the switch, then show
   that a `stresstest`-class chat through the `zuno-stresstest` client creates the Redis keys, that an ai-gateway pod deletion keeps
   the consumed total, and that normal service and Lightspeed are unaffected. Run the probe before and after. Results in
   [wp-157-inventory.md](../evidence/wp-157-inventory.md) (follow-up of 2026-10-25, WP-177 live proof).
4. **Trusted client (done elsewhere).** `TRUSTED_PLATFORM_CLIENTS` is `zuno-stresstest` on demo333 (1e7034ce); `zuno-evaluations`
   no longer selects a quota class. Stress and drill scripts must sign in through `zuno-stresstest`.
5. **Deferred, only if Kuadrant is fixed:** re-run the minimal reproduction and the probe (expect all families to move), then V8
   (cross-model total) and V14 (closed class during a Limitador outage), and only on proven equivalence remove `app/quota.py`,
   `quota_budgets.yaml`, `tests/test_quota_budgets.py`, the ledger calls and `_render_budgets`.

## Checks never run

| Check | Why |
|---|---|
| V2, V3, V5 | They need an ExternalModel with egress (`MAAS_EXTERNAL_EGRESS_ENABLED=false`); the vendor route defect is open. SaaS providers stay direct (ADR-0570 exception). |
| V6 | Personas no longer reach MaaS (401), so the choice among several subscriptions cannot be exercised with a persona token. |
| V11 | Needs a verified project id; a server-resolved one (ADR-0528) is not implemented. |
| Lightspeed counter | Done 2026-10-25: a console question moved `lightspeed-gpt-oss-20b-tokens` (18,346 tokens). |
| Redis outage on the live gateway | Done 2026-10-25 as an in-pod drill with an unreachable Redis; it found and fixed a 4 s stall (facd34e7). |

## Side item

Existing Limitador counters keep the `max_value` they were created with, so a limit change reaches them only when their window
ends; plan any limit change around that.

## Acceptance

The probe reports `subscription` only (or more, if Kuadrant changed), the ledger keeps its budgets across an ai-gateway restart on
demo333 with `QUOTA_LEDGER_STORE=redis`, and normal service is unaffected.
