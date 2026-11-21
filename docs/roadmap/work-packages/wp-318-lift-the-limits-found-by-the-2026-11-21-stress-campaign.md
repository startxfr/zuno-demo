# WP-318: Lift the limits found by the 2026-11-21 stress campaign

- **State:** Not started (planned; the memory of the crash-looping pods is wanted before 2026-11-24 because the chaos health signal watches their namespace, the rest after the demonstration)
- **ADRs:** [ADR-0624](../../adr/0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md), [ADR-0626](../../adr/0626-chaos-engineering-with-krkn-and-tekton-pipelines.md)
- **Depends on:** none
- **Related:** [WP-317](wp-317-improve-the-stress-tool-after-the-2026-11-21-campaign.md) (the tool itself), [WP-316](wp-316-run-chaos-pipelines-and-the-two-chaos-demos.md), [WP-313](wp-313-give-the-stresstest-the-observability-it-needs-to-judge-load.md), [WP-315](wp-315-harden-maas-usage-tiers-single-listener-alert-limitador-redis.md)
- **Target:** v0.18
- **Estimated files touched:** ~10 here, plus a release of zuno-demo-agents: `ansible/inventories/demo333/cluster.yml`, `ansible/roles/openshift_ai/tasks/module_manager_memory.yml` and `right_size_monitoring_stack.yml`, `gitops/charts/kueue/values.yaml`, `gitops/charts/models/values.yaml`, `components/ai-gateway/app/telemetry.py` and `quota.py`, the mcp-gateway's telemetry, the stress personas' UnifAI teams, this brief

## Goal

The stress campaign of 2026-11-21 (09:35 to 10:40 UTC) reached no capacity limit of the platform: it reached limits of
its quotas, of the memory given to some operators, of the batch queue and of the metrics. This work package lifts or
measures them. It changes the platform; the stress tool itself is WP-317.

## The limits found (2026-11-21)

| # | Limit | Where it is set | When |
|---|---|---|---|
| L1 | The `loadtest` quota class is not defined in the agents' quota policy, so the load personas fall in `stresstest` (2,000 tokens per 5 minutes per user) | zuno-demo-agents `policies/quotas/quota-policy.yaml` (a release, then a promotion and an ai-gateway roll) | after 2026-11-24 |
| L2 | The `loadtest` group budget, 1,000,000 tokens an hour, was exhausted | the same policy; distinct group sets for the load personas (`components/ai-gateway/app/quota.py`) | after 2026-11-24 |
| L3 | The gpt-oss-20b `service` tier, 200,000 tokens an hour for the stress ServiceAccount, was exhausted twice | `gitops/charts/models/values.yaml` (a subscription of its own for the stress identity, with the MaaS wasm size check) | after 2026-11-24 |
| L4 | Four pods crash-looped on memory: the dashboard, feast and spark operators (before the load) and the Tempo compactor (at the peak) | `openshift_ai_module_manager_memory` and a patch for the dashboard operator; `openshift_ai_tempostack_memory_limit`; `spec.resources` for Zuno's Tempo | before 2026-11-24 (the chaos health signal fails while a watched pod is not Running) |
| L5 | The Kueue ClusterQueue `default` admits 750m of CPU, so only one two-shard campaign runs at a time (it is an image-pull throttle) | `gitops/charts/kueue/values.yaml` | before 2026-11-24 if the stress and chaos run of 2026-11-22 needs it, otherwise after |
| L6 | The gateways' request-latency histogram tops out at 1 s, so slower answers are not measured | `components/ai-gateway/app/telemetry.py`, the mcp-gateway's telemetry | after 2026-11-24 |
| L7 | The stress personas share UnifAI team workspaces with the demo personas: a demo's ownership check failed during the campaign | the stress personas' UnifAI teams | after 2026-11-24 |
| L8 | 95 % of the Praxis rows of the campaign read `filter_reject` or `route=unknown`: not explained yet | to read in Praxis' logs | after 2026-11-24 |

## Acceptance

- L4: no OOM restart of the four pods in the 24 hours after the change.
- L1 to L3 and L5: a live campaign (owner's go) runs without exhausting a budget it was not meant to test, and two
  campaigns can be admitted together.
- L6: a latency above 1 s is visible in the histogram.
- L7: the demo personas' workspaces hold no stress session.
- L8: explained, with the fix or the known limit written here.
