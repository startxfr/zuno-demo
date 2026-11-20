# WP-314: Fit the MaaS gateway wasm config under 1.4 MB

- **State:** Done (2026-11-20: applied between 12:25 and 12:27 UTC, the EnvoyFilter is at generation 4 and all 20 limits are counted; V4 and V6 passed; the re-check after the KServe window of the same day passed at 15:33 UTC, see below)
- **ADRs:** [ADR-0624](../../adr/0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md)
- **Depends on:** none
- **Related:** [ADR-0521](../../adr/0521-route-local-model-traffic-through-maas.md), [ADR-0570](../../adr/0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md), [ADR-0581](../../adr/0581-derive-stack-configuration-from-the-admitted-corp-bundle.md), [ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md), [WP-306](wp-306-give-the-stress-runs-their-own-identity-and-budget.md), [WP-313](wp-313-give-the-stresstest-the-observability-it-needs-to-judge-load.md)
- **Target:** v0.17
- **Estimated files touched:** ~5: `gitops/charts/models/templates/_llmisvc-route.tpl`, `templates/maas.yaml`, `values.yaml`, two tools under `platform/models/`, this brief and the docs that quote the budgets

## Goal

The EnvoyFilter `openshift-ingress/kuadrant-maas-default-gateway` can be written again, so every MaaS token limit is counted, and it stays far
enough under the API request limit that the next model or subscription does not break it.

## What was found (measured 2026-11-20)

- The EnvoyFilter has been stuck at generation 3 since 2026-11-05. The desired object is 3.92 MB, over the 3 MiB API request limit and the 2 MiB gRPC request limit (1.5 MiB in etcd), so the Kuadrant operator logs "failed to update envoyfilter object" on every change and the data plane serves the 2026-11-05 config.
- Kuadrant writes one wasm action set per route **match** and per **listener** (about 3.6 KB each) plus a reserve/commit pair per **limit** (about 3.9 KB).
  The size model is calibrated on the 73 action sets live.
- 11 of the 29 limits were never counted: `gpt-oss-20b-ocp-ai-dev`, `-ocp-ai-ops`, `-ocp-paas-ops`, the `*-praxis` limits and the `*-load` limits. The descriptor
  key comes from the subscription's name, so a subscription re-created under a name that existed on 2026-11-05 (`sales`, `agents`) was still counted.

## The change (owner decision 2026-11-20; chart commit 43f9eb0a)

1. **Route matches** (`gitops/charts/models/templates/_llmisvc-route.tpl`): 15 matches per model go down to 3. The four per-endpoint rule pairs the KServe
   controller generates are dropped; the catch-all path rule, the catch-all `X-Gateway-Model-Name` rule and the pool anchor remain. Every backend is the same
   workload Service and the catch-all rules rewrite the same paths ([ADR-0521](../../adr/0521-route-local-model-traffic-through-maas.md) note of 2026-11-20).
2. **Praxis** (`altGatewayPeers.praxis.ownSubscription: false`): Praxis's ServiceAccount is a second user of each local `<model>-ai-gateway` subscription. The limits count
   by `auth.identity.userid`, so the two identities keep separate counters of the same size.
3. **`/sales`** is rendered on gpt-oss-20b only (`maas.salesSubscriptions.models`).
4. **`<model>-agents`** is not rendered (`maas.agentSubscriptionTier.enabled: false`). No agent calls MaaS with an `agent_*` identity: the ai-gateway always sends its own
   ServiceAccount. These subscriptions outranked `/sales` (priority 10 against 1), so sale-01 landed on them and the two-tier contrast of ADR-0201 did not hold.
   `values.agents.generated.yaml` and its generator stay ([ADR-0581](../../adr/0581-derive-stack-configuration-from-the-admitted-corp-bundle.md) clause 3).
5. MaaSAuthPolicy subjects are de-duplicated.

Result with the live `zuno-models-d1` values: 28 subscriptions become 17; limits per route: gpt-oss-20b 7, qwen35-9b 3, qwen35-9b-wesh 2, qwen36-27b-instruct 3, each SaaS model 1.
Estimated wasm config about 0.68 MB with both listeners; 27 objects pass a server dry-run. The second listener `https-external` stays: `maas-api` takes the external URL from it
and the portal's API keys page needs it. No Keycloak change and no zuno-demo-agents change.

New tools (zuno-demo-coder, commit 7839b666): `platform/models/maas_wasm_size.py` (the size estimate, with a CI gate at 1.4 MB for demo333's shape) and `platform/models/check_maas_wasm.py`
(a read-only live check: generation, size, COUNTED or NOT USED per limit, the operator's failed-update count), with their tests and a step in `lint.yml`.

## How it was applied (2026-11-20 between 12:25 and 12:27 UTC)

Applied on 2026-11-20 by pushing the chart change and patching the 4 generated HTTPRoutes (`zuno-ai-run/<model>-kserve-route`) to the 3-rule spec rendered from the new LLMInferenceService spec, because the KServe LLMInferenceService reconciler is stopped while its component is being deleted (since 2026-11-19). The chart commits are on `devel` (43f9eb0a chart, 957bd699 comments of `ansible/clusters/demo333.yml`, 7839b666 the two tools; pushed
`5efff7fbc..7839b6661`); the four routes were patched at 12:27:18 to 12:27:21 UTC and the EnvoyFilter was written at 12:27:26 UTC. No Ansible run was needed: every change is in the
chart and the d1 Application values are unchanged. The last refusal of the Kuadrant operator (12:27:11 UTC) was the intermediate state, 2,585,274 bytes against the real gRPC maximum of 2,097,152
bytes, before the route patch.

**After the KServe window**, KServe regenerates each route from `spec.router.route.http.spec` of its LLMInferenceService. That is the user-managed route of ADR-0521, that is the chart template,
now with 3 rules and 3 matches. It rebuilds the same 3-match routes, not the 15-match routes the controller would generate on its own; the direct patch only anticipated what the reconciler will write.

## Checks (results of 2026-11-20)

| # | Check | Expected | Result |
|---|---|---|---|
| V1 | `python3 platform/models/check_maas_wasm.py` | generation 4 or more, size under 1,400,000 bytes, every limit COUNTED, no failed update after the write, `RESULT OK` | Generation 4 written at 12:27:26 UTC, 674,956 bytes (estimate 675,739), 50 action sets; 20 limits COUNTED, 0 NOT USED, 0 NO-KEY (the 17 MaaS subscription limits, the default deny `maas-api-route` and the 2 workstation per-user limits on `zuno-agent-gateway`); no failed-update line after the write |
| V2 | A call without a token, then with the ai-gateway, Praxis and `ai-gateway-stress` ServiceAccount tokens, on each model through the maas Route | 401 without a token; 200 with them | 401 on all 4 models; 200 on all 4 with the three tokens |
| V3 | Limitador counters of each local route | Two counters under `<model>-ai-gateway` (the ai-gateway and Praxis identities), one under `<model>-load`, and the last limit by name counted | On each local route: 3 counters, two under `<model>-ai-gateway` with separate budgets and one under `<model>-load`; `-load`, the last limit by name on the qwen routes, is counted, so the Kuadrant shim defect does not touch the subscription limits |
| V4 | The ADR-0201 contrast, live | sale-01 gets 200 on gpt-oss-20b with a counter under `gpt-oss-20b-sales` and 403 on qwen36-27b-instruct | Passed live on 2026-11-20 (13:53 to 13:54 UTC) with `stress-sale-01`, the twin of sale-01 in the `/sales` group, signed in through the OpenShift `openshift` IdP (a twin, so that no demo persona can be locked). One 5-token chat on gpt-oss-20b returned 200 and the Limitador counter of `gpt-oss-20b-sales` went from 5,000 to 4,925 remaining: the `/sales` tier (5,000 tokens an hour) is counted. On qwen36-27b-instruct it got 403 (no subscription for `/sales` there). Cleanup: its OAuth access token, Identity, User and the 5 groups the login created were deleted; the OpenShift group list is identical to the snapshot taken before |
| V5 | Clients: the golden-path probes, `make demo status` of the affected scenarios | Probes pass; statuses clean | 14 of 14 golden-path probes PASS; `make demo status` PASS for maas-portal-api-keys, genai-playground, quotas, external-models and multi-gateway. Praxis had no client traffic during the checks; its ServiceAccount got 200 directly |
| V6 | `make d2 check agents` on agents v1.1.7, run by zuno-demo-cluster after the change | The acceptance gate passes | OVERALL PASS, failed 0: quality 18/19, security 14/14, gate checks 5/5. The one failure, #11 (RAG citation), was already there on agents v1.1.6 before this change. A real Praxis client call (OpenClaw, consultant-02) also returned 200, with `step="maas" status=200` in the Praxis log |

**Re-check after the KServe window of 2026-11-20 (15:33 UTC, zuno-demo-assist): passed.** KServe regenerated the 4 model routes from the LLMInferenceService spec with 3 rules each (`catch-all-path`, `catch-all-model-routing`, `inference-pool-anchor`). By then the usage tiers of [WP-315](wp-315-harden-maas-usage-tiers-single-listener-alert-limitador-redis.md) were live, so V1 to V3 were measured on them: generation 14, 549,033 bytes, 15 limits COUNTED, 0 NOT USED; 401 without a token and 200 for the platform identities on the 4 models; one counter per tier and per identity.

## Rollback

- **The write still fails (the estimate was wrong).** Generation 3 stays. Its catch-all predicates still match the 3-match routes, so authentication keeps working. Stop and analyse.
- **A subscription problem.** Revert the values part of 43f9eb0a, or set the chart values back: `altGatewayPeers.praxis.ownSubscription: true`, `maas.agentSubscriptionTier.enabled: true`,
  `maas.salesSubscriptions.models: []`. The filter still fits.
- **Do not revert the route template.** It re-inflates the desired object and the write fails again (the real limit is the 2 MiB gRPC request); the reduced filter already written still covers every model path. Fix forward.
- **Authentication broken by the new filter.** zuno-demo-cluster re-applies its generation-3 backup (`oc replace`).

## After the demo, in this order

1. **Full usage tiers**: platform (ai-gateway and Praxis, 1,000,000 tokens an hour), service (Lightspeed and the stress runs, 200,000), builders (the three `ocp-*` groups merged, 5,000,000), business
   (`/sales`, 5,000, gpt-oss-20b). Priorities platform, then builders, then business; about 0.55 MB; the demo pages and the checks are renamed.
2. **Tier definitions in zuno-demo-agents**: `policies/quotas/quota-policy.yaml`, generated into the models chart ([ADR-0511](../../adr/0511-define-okf-quota-policy-enforced-via-kuadrant.md) clause 1,
   [ADR-0570](../../adr/0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md) clause 2), shipped in an agents release.
3. **Model routes on the `https` listener only** (`sectionName`), after a test of the external API-key path. That halves the size again; drop the header catch-all if nothing uses it.
4. **An alert built on `check_maas_wasm.py`**, and Limitador on Redis so the counters survive a restart.
5. The Red Hat support case on the silent failure (a draft exists, on hold by the owner's decision of 2026-11-19).

## Acceptance

- The EnvoyFilter generation moves past 3 and the Kuadrant operator logs no "failed to update envoyfilter object" after a change.
- `check_maas_wasm.py` reports every limit COUNTED, or NOT USED for a subscription that exists on purpose with no traffic.
- The estimate stays under 1.4 MB in CI with demo333's shape.
