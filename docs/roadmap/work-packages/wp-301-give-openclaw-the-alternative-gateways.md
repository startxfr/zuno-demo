# WP-301: Give OpenClaw the alternative gateways

- **State:** Not started
- **ADRs:** [ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)
- **Depends on:** [WP-292](wp-292-deploy-praxis-ai-in-the-alternative-gateways-namespace.md)
- **Related:** [ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)
- **Target:** v0.17
- **Estimated files touched:** ~3: claw.yaml, values, a NetworkPolicy

## Goal

Each OpenClaw persona has a custom provider per alternative gateway next to `zuno`.

## Steps

1. `gitops/charts/openclaw/templates/claw.yaml`: one more `credentials[]` entry (matched by domain) and one more `customProviders[]` entry per alternative gateway.
2. A NetworkPolicy that lets the operator's proxy reach `zuno-ai-gateways:8080`. Check what the operator generates first (`docs/roadmap/evidence/wp-182-openclaw-spike.md`).
3. Live, with the owner's go.

## Acceptance

- With `altGateways` empty, the rendered chart is identical to before (`helm template` diff), and the client's existing golden-path probe passes.
- With the Praxis entry, the alternative connection is listed in the client and answers a C1 question; a trace of the call is in Tempo under the Praxis service.
- `zuno-demo-reorg` is told before the client rolls, so its offline walkthrough suite is re-run for this client.
