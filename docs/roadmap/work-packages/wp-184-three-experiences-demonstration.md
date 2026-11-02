# WP-184: Three-experiences demonstration

- **State:** Not started
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

## Acceptance

The script runs end to end on demo333 and the evidence shows, from raw Prometheus, one series per client for the same
persona, a guardrail hit and a 429 in each experience.
