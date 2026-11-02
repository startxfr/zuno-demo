# WP-184: Three-experiences demonstration

- **State:** Repo work in review (dashboard and script in the repository 2026-11-02; the live run and the shared-quota proof are not done)
- **ADRs:** [ADR-0587](../../adr/0587-admit-additional-user-experiences-over-the-one-governed-backend.md), [ADR-0588](../../adr/0588-serve-a-general-purpose-chat-experience-with-open-webui.md), [ADR-0589](../../adr/0589-serve-per-persona-openclaw-assistants-via-claw-operator-behind-a-token-injecting-egress-proxy.md)
- **Depends on:** [WP-181](wp-181-install-open-webui-on-demo333.md), [WP-183](wp-183-install-openclaw-on-demo333.md)
- **Related:** [WP-179](wp-179-common-preparation-for-experience-clients.md)
- **Target:** v0.13
- **Estimated files touched:** ~4 (`gitops/charts/{grafana,perses}` dashboard "Three experiences", `docs/demo/three-experiences.md`, evidence)

> Joint closing package, done by one session once both tracks are Done. Closes ADR-0587, ADR-0588 and ADR-0589.

## Steps

1. **Dashboard "Three experiences"** on WP-179's panels: tokens, cost, calls and guardrail hits per `client` and per
   `user`, the persona's quota consumption, a link to the run traces.
2. **Demo script** `docs/demo/three-experiences.md`: one persona asks the same question in Open WebUI, in its OpenClaw and
   to a UnifAI agent; show the same model list, the same tool allowed and the same tool refused, the same guardrail, the
   dashboard.
3. **Shared quota.** With a persona whose ceiling is lowered for the run, spend the budget in one experience and get 429 in
   the other two (for OpenClaw, the persona's assistant identity, ADR-0589 consequences); restore the ceiling.
4. **Close.** Evidence file; ADR-0587, ADR-0588, ADR-0589 to `Implemented`; WP-179 to WP-184 to Done.

## Repository work (2026-11-02)

- Dashboard **Three experiences**: `gitops/charts/grafana/templates/dashboard-three-experiences.yaml` and its Perses
  translation `gitops/charts/perses/templates/dashboard-three-experiences.yaml`; variables `client` and `user`; rows *Same
  backend, three experiences* (calls, tokens, cost, guardrails by client), *Same models, same routing* (provider per client,
  candidates skipped for availability, ADR-0591), *Same user, one budget* (a user's tokens across clients).
- Script: [docs/demo/three-experiences.md](../../demo/three-experiences.md), one persona (sale-01) through the three
  experiences, eight steps, with the GPU-down case.
- User decision of 2026-11-02: repository only for now; the shared-quota proof (step 3) waits for a rehearsal.
- Rehearsal attempt of 2026-11-02 (GPU nodes down): `QUOTA_REHEARSAL_GROUP` (ai-gateway build 34) put sale-01 in the tight
  `stresstest` class; three Open WebUI chats returned 502, 502, 200 (the 200 after the pod rolled and the group env was gone).
  The gateway skipped every SaaS candidate and every direct local sibling because `stresstest` is `fail_mode: closed`, and the
  MaaS local models were not ready, so no token was counted. Reverted the same evening. Step 3 needs the local models back,
  or a tight class with `fail_mode: open`; it stays open.
- Open WebUI pass of 2026-11-02 22:37 UTC (steps 1, 2, 6 and 7 as sale-01 and finance-01, fresh Keycloak sessions, SaaS at C1):
  both personas sign in with role `user` and see the 11 models; the tool lists are sale-01 `drive.document.search`,
  `gmail.message.read`, `diagram.generation.create` and finance-01 the first two; a short chat answers in 1 s for both; the
  injection prompt answers 200 in `observe` mode. Raw Prometheus (thanos-querier, after the 22:31 pod restart reset the
  counters): `zuno_model_calls_total{client="open-webui",provider="openai"}` 2 and
  `zuno_guardrails_evaluations_total{client="open-webui",outcome="detected"}` 1, the export lagging by about a minute.
- OpenClaw pass of 2026-11-02 (steps 1, 2 and 6 on sale-01's assistant, run by the OpenClaw session as the assistant itself,
  standard class): the short chat answered "pong" through the gateway path (model fetch HTTP 200 in 1.3 s, provider `openai`
  gpt-4o-mini, C1); `tools/list` returned `drive.document.search`, `gmail.message.read` and `diagram.generation.create`, and
  `tools/call confluence.page.search` returned `isError=true` (not exposed through the MCP endpoint, ADR-0524 front-door
  allowlist / ADR-0571 agent declaration). Raw Prometheus: `zuno_model_tokens_total{client="openclaw-sale-01",provider="openai"}`
  42 at query time, the pong turn not yet scraped. Not yet rehearsed: the UnifAI steps (sale-01 has no chat session and the
  script does not name the agent to ask) and the 429 of step 8.

## Acceptance

The script runs end to end on demo333 and the evidence shows, from raw Prometheus, one series per client for the same
persona, a guardrail hit and a 429 in each experience.

- Shared-quota rehearsal of 2026-11-03 (GPU models back; sale-01 and `service-account-openclaw-sale-01` in the group
  `zuno-quota-rehearsal`, `QUOTA_REHEARSAL_GROUP` set live, class `stresstest`, 2,000 tokens per user per 5 minutes; reverted
  after the run, an empty group left in Keycloak). OpenClaw (azp `openclaw-sale-01`): 3 turns 200 (666 tokens, 23:15:15-39), a
  big turn 200 at 23:17:13 (1,520 tokens, total 2,186 of 2,000), then 429 at 23:18:41-42 (3 calls). Open WebUI as sale-01
  (fresh sign-in): 429 at about 23:18:40 with the same body `{"error":"quota_exceeded","quota_class":"stresstest","dimension":"user",
  "budget_tokens":2000,"window":"5m"}`. **Caveat:** the ledger keys the user budget by the token's `sub`
  (`components/ai-gateway/app/quota.py`, `check`/`consume`), and OpenClaw calls as a service account, a different `sub`. The
  Open WebUI 429 therefore proves that sale-01's own counter was spent (by my earlier chats of 23:15-23:18, whose status I did
  not capture), not that OpenClaw's spending drained it. One counter shared by the three experiences is not what the
  platform does for the user dimension; the group dimension is common to the persona's accounts. UnifAI was not exercised.
  Raw Prometheus (cumulative since the pod roll): `zuno_model_tokens_total` open-webui 146 (openai) + 12,188 (local-maas),
  openclaw-sale-01 57,507 (openai) + 2,664 (local-maas), unifai 2,116,676 (local-gpt-oss-maas); one series per client.
