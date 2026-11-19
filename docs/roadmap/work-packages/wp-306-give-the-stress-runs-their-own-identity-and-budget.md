# WP-306: Give the stress runs their own identity and budget

- **State:** Repo work in review (2026-11-19, committed in the `wp306-coder` worktree, not pushed); the rolls and the live proof are the reviewer's, each with the owner's go and a notice to zuno-demo-cluster
- **ADRs:** [ADR-0624](../../adr/0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md)
- **Depends on:** [WP-305](wp-305-build-the-stress-runner-core-and-profiles.md), [WP-307](wp-307-launch-the-stress-campaign-as-an-indexed-job.md)
- **Related:** WP-308, WP-309, WP-313
- **Target:** v0.17
- **Estimated files touched:** ~20: the ai-gateway and mcp-gateway code and tests, the ai-gateway, models and keycloak charts, two Ansible roles, the quota policy of zuno-demo-agents (outside this repository)

## Goal

A load run spends a budget of its own, on a MaaS identity of its own, and its traffic is recognisable in the traces. The 2026-11-19 stresstest drained the ai-gateway ServiceAccount's MaaS budget (1,000,000 tokens an hour per model route, one Limitador counter for every caller of the gateway) and Open WebUI, Dify, kagent and OpenClaw answered 429 until about 01:22 UTC: that must not be possible again.

## Steps

1. **Quota class `loadtest`.** Its definition belongs to the quota policy, which lives in the zuno-demo-agents repository (`policies/quotas/quota-policy.yaml`, released as the OCI bundle pinned by `platform/okf/agents.lock`), not in this tree. The block to add there is in the progress note below. Once a release carries it: promote it, then regenerate `components/ai-gateway/app/quota_budgets.yaml`, `quota_fail_modes.yaml`, `quota_windows.yaml` and the two connectivity-link templates with `python3 platform/okf/generate_quota_enforcement.py --release-dir <release>` (no generator change: it selects a class by the `x-zuno-quota-class` header, whatever its name). Until then the code below is inert: a group naming a class the budgets do not define is ignored.
2. **The ai-gateway** (`components/ai-gateway/app`):
   - `main.py` `_default_quota_class`: members of `QUOTA_LOADTEST_GROUP` run under `loadtest`, checked before the stresstest and evaluation groups, and only when the budgets define the class;
   - `maas_adapter.py`: `MAAS_CLASS_TOKEN_PATHS` (a JSON object `{class: token file}`) gives a quota class its own MaaS credential. `_maas_bearer_token(caller_token, quota_class)` and `chat_model_via_maas` send it, whatever the gateway-identity switch says, and a mapped class whose file is missing or empty raises: there is no fallback to the ai-gateway ServiceAccount. `main.py` passes the class on the metered `/v1/messages` and `/v1/responses` path as well;
   - `telemetry.py`: the optional header `X-Zuno-Traffic: stresstest` becomes the span attribute `zuno.traffic` on `model_call` and `guardrails_observe`. It is read once per request by `adopt_incoming_trace_context` (already on every endpoint), only the value `stresstest` is kept, and it is never a metric label. Query it in Tempo with `{ span.zuno.traffic = "stresstest" }`.
3. **The mcp-gateway** (`components/mcp-gateway/app/telemetry.py`): the same tag on `tool_invoke`.
4. **Charts, all off by default** (the default render is identical to before for the ai-gateway and models charts):
   - `models`: `altGatewayPeers.stress` renders a `<model>-load` MaaSSubscription per local model for the ServiceAccount `zuno-ai-run/ai-gateway-stress`, with its own limit (200,000 tokens an hour, priority 50, not a copy of the ai-gateway's), and the MaaSAuthPolicy admits it;
   - `ai-gateway`: `maasAdapter.classCredentials` renders that ServiceAccount and a `kubernetes.io/service-account-token` Secret (filled in by the token controller, nothing committed), mounts it at `/var/run/secrets/maas-stress` and sets `MAAS_CLASS_TOKEN_PATHS` for the listed classes (`loadtest`, `stresstest`); `quotaLoadtestGroup` sets `QUOTA_LOADTEST_GROUP`;
   - `keycloak`: the pool `stress-load-01` to `stress-load-08` (copies of consultant-01, in `/zuno-evaluation` like every evaluation persona, plus `/zuno-loadtest` through the new `extraGroups`); the Job creates the groups listed in `evalPersonasExtraGroups`.
5. **Ansible**: one switch, `zuno_ai_gateway_stress_credentials` (the llm and models roles), and `zuno_ai_gateway_quota_loadtest_group` (the llm role). Neither is set in `ansible/clusters/demo333.yml`: turning them on is the roll below.
6. **Runner**: the load profiles name the pool with `STRESS_PERSONAS` (a comma list). The drivers already send `X-Zuno-Quota-Class: stresstest`; once the class exists the pool is placed in it by its group, with no header at all, and the traffic tag is already sent.

## Acceptance

Offline, done: `components/ai-gateway/tests/test_wp306_stress_identity.py` (14 cases), `components/mcp-gateway/tests/test_traffic_tag.py` (4), the existing ai-gateway and mcp-gateway suites unchanged, `platform/keycloak/tests` (18, one new), `helm template` of the three charts identical to before by default and rendering the new objects when switched on, `python3 platform/docs/check_docs.py`.

Live, with the owner's go, in this order (each roll announced to zuno-demo-cluster first):

1. zuno-demo-agents: a release defining `loadtest`; promote it, regenerate, commit the generated files.
2. Rebuild and roll the ai-gateway and mcp-gateway images (a code change in both).
3. `make d1 install`/`make d2 install models` with `zuno_ai_gateway_stress_credentials: true`: the `<model>-load` subscriptions appear and the MaaS gateway admits the ServiceAccount (`oc get maassubscription -n models-as-a-service | grep stress`).
4. The Keycloak personas Job (create-only: the pool and `/zuno-loadtest` appear, nothing is removed).
5. `make d2 install llm` with the same switch and `zuno_ai_gateway_quota_loadtest_group: zuno-loadtest`: the second ServiceAccount, its token Secret and `MAAS_CLASS_TOKEN_PATHS` appear; the Secret gets its `token` key from the token controller (check `oc get secret ai-gateway-stress-token -o jsonpath='{.data.token}'` is not empty; the gateway raises and answers 502 on a mapped class if it is).
6. **Isolation proof**: read the counters of the ai-gateway ServiceAccount's MaaS subscription before and after a `make d3 stresstest PROFILE=standard` run on the pool, and show them unchanged while the `<model>-load` ones moved. Limitador's per-limit counters are what carry this (its admin API lists a namespace's counters with their remaining quota: confirm the route on this Limitador build; WP-313 owns a permanent reader). Cross-check in Tempo: the run's spans carry `zuno.traffic = stresstest`, and the Authorino metrics or the MaaS gateway access log show requests as `ai-gateway-stress`, none as `ai-gateway`. Then run the golden-path probes of Open WebUI, Dify and kagent during the run: none may answer 429.

## Open points

- The numbers of the `loadtest` class (proposal below) are a decision of the owner; the ADR gives none. The MaaS side is capped independently by the `<model>-load` limit of the models chart.
- Praxis is a second MaaS consumer with its own ServiceAccount and subscriptions (`altGatewayPeers.praxis`). It injects its own credential whatever token the caller sends, so stress traffic through Praxis spends the Praxis budget, not the stress one. Until Praxis can pick a credential by caller, the Praxis drivers of WP-308 stay low rate and behind the budget guard.
- The token Secret of the second ServiceAccount is a long-lived token; rotate it by deleting the Secret. A Vault-backed variant (ExternalSecret) fits the same mount if the owner prefers it.

## The per-agent Jobs and the shared budget (2026-11-19)

The standard run of 2026-11-19 left the shared ai-gateway ServiceAccount's MaaS counter at 1,002,556 / 1,000,000 and broke `make d2 check agents`: the per-agent Jobs (family `agents`, signing in as the `stress-<persona>` twins) and the experience drivers ride that counter. What changed (commit 8a5c6b90 and its follow-up):

- the five stress twins join `/zuno-loadtest` (keycloak chart, `extraGroups`), so the per-agent Jobs run under `loadtest` on the `ai-gateway-stress` identity. Live only after a keycloak roll and the eval-personas Job;
- until that is verified live, `agents` is in no profile (opt-in with `FAMILIES=agents`);
- the experience drivers are capped at 1 iteration and the profiles' `shared_budget_guard` skips a driver of the families experiences, unifai and guardrails when the shared counter is already 50% spent; an unreadable Limitador is one `shared-budget-unknown` WARNING row (the guard is skipped, the run goes on);
- the isolation row of the counters report warns when the shared account moved more than 10% of its window budget.

**Caveat, by design.** `loadtest` is `fail_mode: closed` and served only through MaaS: the ai-gateway skips every SaaS candidate ("not reached through MaaS, skipped for closed quota class 'loadtest'"). A per-agent scenario that needs a SaaS model (for instance tekos #21, Codestral) therefore fails once the twins are in the class. The report lists such rows under "SKIPPED BY DESIGN" with the label "skipped: SaaS under loadtest", not as failures. The class budget (250,000 tokens per user and 1,000,000 per group per hour) is shared by the five twins; whether the agents family fits in it is not verified.

## Progress notes

Proposed block for `policies/quotas/quota-policy.yaml` of zuno-demo-agents (to hand to that session; sized so the `loadtest` pool can carry real load while the MaaS limit of the models chart stays the binding one):

```yaml
  loadtest:
    description: >-
      Load, saturation and soak campaigns of the stress runner (ADR-0624): the stress-load-NN personas, which the
      ai-gateway places here through the /zuno-loadtest group. Its own budget, on its own MaaS ServiceAccount
      (ai-gateway-stress, subscribed per model route by the models chart), so a campaign never spends the ai-gateway
      ServiceAccount's budget that Open WebUI, Dify, kagent and OpenClaw share. fail_mode closed: the class is served
      only through MaaS, where that dedicated identity and its limit apply; a SaaS or unmetered candidate is skipped.
    fail_mode: closed
    requests:
      user:    { limit: 120,  window: 5m }
      group:   { limit: 600,  window: 5m }
      project: { limit: 300,  window: 5m }
    tokens:
      user:    { budget: 250000,  window: 1h }
      group:   { budget: 1000000, window: 1h }
      project: { budget: 500000,  window: 1h }
```

2026-11-19 (live, demo333): the first live proof showed the isolation of the ai-gateway side but no Limitador counter for the stress ServiceAccount on any route: the subscriptions were first named `<model>-stress`, whose limit names sort last, and the Kuadrant wasm shim never creates a counter for the last token-limit action of a route (ordered by limit name). They are renamed `<model>-load`, which sorts between `lightspeed` and `ocp-*`; `sales` stays last as before. Do not name a new subscription so that it sorts after `sales`.
