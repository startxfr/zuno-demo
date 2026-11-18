# WP-300: Give Dify the alternative gateways

- **State:** Not started
- **ADRs:** [ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)
- **Depends on:** [WP-297](wp-297-give-kagent-the-alternative-gateways-through-the-token-proxy.md)
- **Related:** [ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)
- **Target:** v0.17
- **Estimated files touched:** ~3: the dify role defaults and configure.py

## Goal

Dify has a model `<name>-auto` per alternative gateway, on the token-proxy's alternate route.

## Steps

1. `ansible/roles/dify/files/configure.py` and `defaults/main.yml` register `<name>-auto` with the endpoint `<proxy>/alt/<name>/v1`. The name is distinct because models are indexed by name.
2. Live, with the owner's go: run the Dify configure step.

## Acceptance

- With `altGateways` empty, the rendered chart is identical to before (`helm template` diff), and the client's existing golden-path probe passes.
- With the Praxis entry, the alternative connection is listed in the client and answers a C1 question; a trace of the call is in Tempo under the Praxis service.
- `zuno-demo-reorg` is told before the client rolls, so its offline walkthrough suite is re-run for this client.
