# WP-296: Give Open WebUI the alternative gateways

- **State:** Not started
- **ADRs:** [ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)
- **Depends on:** [WP-292](wp-292-deploy-praxis-ai-in-the-alternative-gateways-namespace.md)
- **Related:** [ADR-0587](../../adr/0587-admit-additional-user-experiences-over-the-one-governed-backend.md)
- **Target:** v0.17
- **Estimated files touched:** ~4: values, the deployment env, the egress NetworkPolicy

## Goal

Open WebUI lists the alternative gateways' models next to "Zuno", each prefixed with its gateway's label, under the user's own token.

## Steps

1. `altGateways` in `gitops/charts/open-webui/values.yaml`. Each entry:
   - appends to `openaiBaseApiUrls`;
   - adds an `OPENAI_API_CONFIGS` index with `prefix_id` and `auth_type: system_oauth`.
2. An egress rule to `zuno-ai-gateways:8080` in `templates/networkpolicy-egress.yaml`.
3. Check `BYPASS_MODEL_ACCESS_CONTROL`: the alternative models are visible to the same users as "Zuno".
4. Live, with the owner's go: roll Open WebUI.

## Acceptance

- With `altGateways` empty, the rendered chart is identical to before (`helm template` diff), and the client's existing golden-path probe passes.
- With the Praxis entry, the alternative connection is listed in the client and answers a C1 question; a trace of the call is in Tempo under the Praxis service.
- `zuno-demo-reorg` is told before the client rolls, so its offline walkthrough suite is re-run for this client.
