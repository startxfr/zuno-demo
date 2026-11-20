# WP-314: Fit the MaaS gateway wasm config under 1.4 MB

- **State:** Not started (2026-11-20: the repository change is committed and reviewed locally and is not in `devel` yet; it is pushed and applied in the 2026-11-21 KServe window, with the owner's go and a notice to zuno-demo-cluster)
- **ADRs:** [ADR-0624](../../adr/0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md)
- **Depends on:** none
- **Related:** [ADR-0521](../../adr/0521-route-local-model-traffic-through-maas.md), [ADR-0570](../../adr/0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md), [ADR-0581](../../adr/0581-derive-stack-configuration-from-the-admitted-corp-bundle.md), [ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md), [WP-306](wp-306-give-the-stress-runs-their-own-identity-and-budget.md), [WP-313](wp-313-give-the-stresstest-the-observability-it-needs-to-judge-load.md)
- **Target:** v0.17
- **Estimated files touched:** ~5: `gitops/charts/models/templates/_llmisvc-route.tpl`, `templates/maas.yaml`, `values.yaml`, two tools under `platform/models/`, this brief and the docs that quote the budgets

## Goal

The EnvoyFilter `openshift-ingress/kuadrant-maas-default-gateway` can be written again, so every MaaS token limit is counted, and it stays far
enough under the API request limit that the next model or subscription does not break it.

## What was found (measured 2026-11-20)

- The EnvoyFilter has been stuck at generation 3 since 2026-11-05. The desired object is 3.92 MB, over the 3 MiB API request limit and the 1.5 MiB etcd
  request limit, so the Kuadrant operator logs "failed to update envoyfilter object" on every change and the data plane serves the 2026-11-05 config.
- Kuadrant writes one wasm action set per route **match** and per **listener** (about 3.6 KB each) plus a reserve/commit pair per **limit** (about 3.9 KB).
  The size model is calibrated on the 73 action sets live.
- 11 of the 29 limits were never counted: `gpt-oss-20b-ocp-ai-dev`, `-ocp-ai-ops`, `-ocp-paas-ops`, the `*-praxis` limits and the `*-load` limits. The descriptor
  key comes from the subscription's name, so a subscription re-created under a name that existed on 2026-11-05 (`sales`, `agents`) was still counted.

## The change (owner decision 2026-11-20; commit c7c69b65 on the local branch `maas-wasm-fit`, pushed during the window)

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

New tools (zuno-demo-coder, commit cdb39c0b): `platform/models/maas_wasm_size.py` (the size estimate, with a CI gate at 1.4 MB for demo333's shape) and `platform/models/check_maas_wasm.py`
(a read-only live check: generation, size, COUNTED or NOT USED per limit, the operator's failed-update count), with their tests and a step in `lint.yml`.

## Steps (2026-11-21, KServe window)

The window is run by zuno-demo-cluster, with the owner's go per step in its session. The commits are on the local branch `maas-wasm-fit` (c7c69b65 chart, 6bc7d4c2 comments of
`ansible/clusters/demo333.yml`, cdb39c0b the two tools); their SHAs can change when that branch is rebased before the push.

1. **Backups, then the guard G2.** zuno-demo-cluster creates a ValidatingAdmissionPolicy and its binding that refuse UPDATE and DELETE of the EnvoyFilter
   `openshift-ingress/kuadrant-maas-default-gateway`. While the four LLMInferenceServices are deleted their routes are gone, and the Kuadrant operator would otherwise write a small
   filter without the action set of the model routes. G2 keeps generation 3 meanwhile. The names are in zuno-demo-cluster's window plan.
2. **Freeze and delete.** Auto-sync of the Application `zuno-models-d1` is frozen, the 4 LLMInferenceServices are deleted, the KServe finalizers are released, the new `default-kserve` is applied.
3. **Push the WP-314 commits to `devel`**, verified with `git ls-remote`. Nothing happens on the cluster yet because the auto-sync of `zuno-models-d1` is frozen. No Ansible run is
   needed: every change is in the chart (templates and chart `values.yaml`) and the d1 Application values are unchanged.
4. **Lift G2** (the policy and its binding are deleted), **restore the auto-sync of `zuno-models-d1` and sync it.** It is the only Application that changes; the MaaS gateway
   (`zuno-openshift-ai-d1`) is untouched. The models come back with 3-match routes, the maas-controller recompiles the 17 subscriptions into the `maas-trlp-*` policies, and the
   Kuadrant operator writes the full EnvoyFilter.

## Checks

| # | Check | Expected |
|---|---|---|
| V1 | `python3 platform/models/check_maas_wasm.py` | `kuadrant-maas-default-gateway` at generation 4 or more, size under 1,400,000 bytes (estimate 675,739), every limit COUNTED (17 MaaS, the default deny and 2 workstation), 0 "failed to update envoyfilter object" in the last 30 minutes, `RESULT OK` |
| V2 | Per model, a call without a token to `https://maas.<cluster domain>/zuno-ai-run/<model>/v1/models`; the golden-path probes through the ai-gateway | 401 (or 403) without a token; 200 through the ai-gateway |
| V3 | Limitador counters: `oc -n kuadrant-system exec deploy/limitador-limitador -- curl -s localhost:8080/counters/zuno-ai-run%2F<model>-kserve-route` | After one ai-gateway call and one Praxis call, two counters under the `<model>-ai-gateway` limit (two identities, two budgets); after one `loadtest` call, a counter under `<model>-load`; after one call with ai-dev-01's portal key, a counter under `gpt-oss-20b-ocp-ai-dev`. The last limit by name on each route (`load` on the qwen models, `sales` on gpt-oss-20b) must show a counter; if it does not, put `/sales` back on the three qwen models as the trailing limit (`maas.salesSubscriptions.models`), on the owner's go |
| V4 | The ADR-0201 contrast | sale-01 gets 200 on gpt-oss-20b with a counter under `gpt-oss-20b-sales` (5,000 tokens an hour), and 403 on qwen36-27b-instruct (no subscription) |
| V5 | Clients: `python3 evaluations/golden_path_probe.py` on every moment, Lightspeed included; one Praxis call per local model; `make demo status` for maas-portal-api-keys, genai-playground, quotas and external-models | Probes pass; the Praxis log shows `sub-request complete step="maas" status=200`; the demo statuses are clean |
| V6 | `make d2 check agents`, run by zuno-demo-cluster | The acceptance gate passes |

## Rollback

- **The write still fails (the estimate was wrong).** Generation 3 stays. Its catch-all predicates still match the 3-match routes, so authentication keeps working. Stop and analyse; re-arm G2.
- **A subscription problem.** Revert the values part of c7c69b65, or set the chart values back: `altGatewayPeers.praxis.ownSubscription: true`, `maas.agentSubscriptionTier.enabled: true`,
  `maas.salesSubscriptions.models: []`. The filter still fits.
- **Do not revert the route template.** It re-inflates the desired object and the write fails again; the reduced filter already written still covers every model path. Fix forward.
- **Authentication broken by the new filter.** zuno-demo-cluster re-applies its generation-3 backup (`oc replace`) and re-arms G2.

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
