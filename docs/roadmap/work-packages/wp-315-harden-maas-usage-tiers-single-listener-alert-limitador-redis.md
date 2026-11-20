# WP-315: MaaS hardening: usage tiers, single-listener test, wasm-config alert, Limitador on Redis

- **State:** Not started (2026-11-20: owner-approved, applied in the evening of the same day, step by step, each with the owner's go and a notice to zuno-demo-cluster; the results are recorded below as they come)
- **ADRs:** [ADR-0624](../../adr/0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md)
- **Depends on:** [WP-314](wp-314-fit-the-maas-gateway-wasm-config-under-1-4-mb.md)
- **Related:** [ADR-0570](../../adr/0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md), [ADR-0511](../../adr/0511-define-okf-quota-policy-enforced-via-kuadrant.md), [ADR-0201](../../adr/0201-complete-the-openshift-ai-maas-governance-plane-integration.md), [WP-310](wp-310-evaluate-the-demos-state-checks-from-the-stress-job.md)
- **Target:** v0.17
- **Estimated files touched:** ~12: `gitops/charts/models/` (templates and values), the MaaS gateway, a CronJob and a PrometheusRule, a Limitador Redis, `platform/models/check_maas_wasm.py`, this brief, and the scenario pages that quote the subscriptions

## Goal

After [WP-314](wp-314-fit-the-maas-gateway-wasm-config-under-1-4-mb.md) every MaaS limit is counted, but the gateway's wasm config is still the object that broke, and its budgets are many and named after
single identities. This work package gives the budgets a lasting shape, tests the next size reduction, watches the object, and makes the counters survive a restart.

## 1. Usage tiers (chart change, applied about 15:45 UTC)

The owner's principles: usage profiles, not per-user subscriptions; one window; exclusive predicates; the MaaSAuthPolicy subjects are derived from the subscriptions; the default deny is kept.

| Tier | Who | Limit | Priority | Models |
|---|---|---|---|---|
| `<model>-platform` | the ai-gateway ServiceAccount and the Praxis ServiceAccount | 1,000,000 tokens an hour | 100 | all 6 models; Praxis on the local models only |
| `<model>-service` | the Lightspeed ServiceAccount and the `ai-gateway-stress` ServiceAccount | 200,000 tokens an hour | 50 | the local models; Lightspeed on gpt-oss-20b, qwen35-9b and qwen36-27b |
| `gpt-oss-20b-builders` | the groups `ocp-ai-dev`, `ocp-ai-ops` and `ocp-paas-ops` | 5,000,000 tokens an hour | 20 | gpt-oss-20b |
| `gpt-oss-20b-business` | the group `/sales` | 5,000 tokens an hour | 1 | gpt-oss-20b |

They replace `<model>-ai-gateway`, `<model>-lightspeed` and `<model>-load`, the three `ocp-*` subscriptions and `<model>-sales`. Estimate from the rendered chart: 550,448 bytes, 12 subscription limits plus the default deny.
The tier is the unit of delegation; this amends [ADR-0570](../../adr/0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md) (dated note).

Result: the chart is on `devel` since 2026-11-20 15:01 UTC (7b289ce5); it goes live when the `zuno-models-d1` auto-sync is restored after the KServe window (about 15:12 UTC). The names, `owner.users`, limit count and bytes measured on the cluster are recorded here after that; until then the figures above are estimates, not measurements.

## 2. Single-listener test (about 16:30 UTC)

A throwaway route attached to the `https` listener only, called through the maas Route, to learn whether the model routes can stay on one listener (`sectionName`), which would halve the wasm config again.
The second listener `https-external` stays for now: `maas-api` takes the external URL from it and the portal's API keys page needs it.

Result to record: applied, or deferred with the reason.

## 3. Alert on the wasm config

A CronJob runs `platform/models/check_maas_wasm.py` every 15 minutes, and the PrometheusRule `ZunoMaasWasmConfigNotApplied` fires when the EnvoyFilter is not the generation the operator wants,
is over the size gate or has a limit NOT USED (zuno-demo-coder). The runbook lines (what to do when it fires) are written here once the alert exists.

Result: pending.

## 4. Limitador on a dedicated Redis (about 17:45 UTC)

A Redis in `kuadrant-system` dedicated to Limitador, so the counters survive a Limitador restart. The price is a dependency: a Redis outage fails part of the MaaS calls.

Result: pending.

## Related work

The image-proof guard (a ValidatingAdmissionPolicy and a deny-all NetworkPolicy) belongs to the mutating drivers of [WP-310](wp-310-evaluate-the-demos-state-checks-from-the-stress-job.md). The aggressive chaos run, first planned for the evening of 2026-11-20, is moved to after the demonstration (owner's decision of the same day); it is not part of this work package, and its evidence file will go under `docs/roadmap/evidence/` when it runs.

## Acceptance

- Each step above records its result here, with the date and time, and the check that proves it.
- The pages that quote the subscriptions follow the tiers: the API keys, playground, quotas, Lightspeed, external models, multi-gateway and agents-alt-gateway scenarios, the demo-day MaaS row and the stresstest runbook.
