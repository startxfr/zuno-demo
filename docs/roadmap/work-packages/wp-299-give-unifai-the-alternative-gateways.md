# WP-299: Give UnifAI the alternative gateways

- **State:** Not started
- **ADRs:** [ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)
- **Depends on:** [WP-292](wp-292-deploy-praxis-ai-in-the-alternative-gateways-namespace.md)
- **Related:** [ADR-0560](../../adr/0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md)
- **Target:** v0.17
- **Estimated files touched:** ~4: values, _helpers.tpl, objects.yaml

## Goal

UnifAI shows one built-in LLM per alternative gateway next to `zuno-gateway`, under the user's own token.

## Steps

1. `altGateways` in `gitops/charts/unifai/values.yaml`: one extra UnifaiLLM per entry in `templates/objects.yaml`, with `forward_user_token: true` and `routingLookup` off (`/routing-decisions` exists only on the Zuno ai-gateway).
2. Add `.zuno-ai-gateways.svc` to `stack.outboundAllowedHosts`, and the egress rule.
3. Live, with the owner's go.

## Acceptance

- With `altGateways` empty, the rendered chart is identical to before (`helm template` diff), and the client's existing golden-path probe passes.
- With the Praxis entry, the alternative connection is listed in the client and answers a C1 question; a trace of the call is in Tempo under the Praxis service.
- `zuno-demo-reorg` is told before the client rolls, so its offline walkthrough suite is re-run for this client.
