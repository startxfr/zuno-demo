# WP-303: Give world-model the alternative gateways

- **State:** Not started
- **ADRs:** [ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)
- **Depends on:** [WP-292](wp-292-deploy-praxis-ai-in-the-alternative-gateways-namespace.md)
- **Related:** [ADR-0604](../../adr/0604-introduce-an-interactive-generative-world-model-experience.md)
- **Target:** v0.17
- **Estimated files touched:** ~5: world-model-web config and prompts, the chart

## Goal

The world-model web app can use an alternative gateway for prompt enhancement.

## Steps

1. `altGateways` in `gitops/charts/world-model/values.yaml`, plus the egress rule.
2. `components/world-model-web/app/config.py` and `prompts.py`: a list of gateways and a selector, defaulting to the Zuno ai-gateway.
3. Tests, then live with the owner's go. The GPU node is not touched.

## Acceptance

- With `altGateways` empty, the rendered chart is identical to before (`helm template` diff), and the client's existing golden-path probe passes.
- With the Praxis entry, the alternative connection is listed in the client and answers a C1 question; a trace of the call is in Tempo under the Praxis service.
- `zuno-demo-reorg` is told before the client rolls, so its offline walkthrough suite is re-run for this client.
