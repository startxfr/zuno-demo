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

## Acceptance

The script runs end to end on demo333 and the evidence shows, from raw Prometheus, one series per client for the same
persona, a guardrail hit and a 429 in each experience.
