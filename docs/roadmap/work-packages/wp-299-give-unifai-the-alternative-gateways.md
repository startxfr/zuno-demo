# WP-299: Give UnifAI the alternative gateways

- **State:** Repo work merged (2026-11-19): the chart renders one shared UnifaiLLM `zuno-gateway-<name>` per entry (forward_user_token, no routing lookup) and adds `.zuno-ai-gateways.svc` to `stack.outboundAllowedHosts`; the role default `zuno_unifai_alt_gateways: []` is combined into the Application values only when not empty. The live steps wait for the owner's go
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

## Repo work (2026-11-19)

UnifAI: the chart renders one shared UnifaiLLM `zuno-gateway-<name>` per entry (forward_user_token, no routing lookup) and adds `.zuno-ai-gateways.svc` to `stack.outboundAllowedHosts`; the role default `zuno_unifai_alt_gateways: []` is combined into the Application values only when not empty. Proofs offline: `helm template` with `altGateways` empty is identical to the chart before the change (0 diff lines) and, with the Praxis entry `{name: praxis, label: Praxis, url: http://praxis.zuno-ai-gateways.svc:8080/v1, models: [auto]}`, adds only the objects above; the role's values expression renders without the key for an empty list and with `altGateways` only for a non-empty one (rendered through Ansible for both); `ansible-playbook --syntax-check` of `day2_install.yml`; `check_docs.py`. The demo333 entry in `ansible/clusters/demo333.yml` is NOT added: it comes at the live step.

## Acceptance

- With `altGateways` empty, the rendered chart is identical to before (`helm template` diff), and the client's existing golden-path probe passes.
- With the Praxis entry, the alternative connection is listed in the client and answers a C1 question; a trace of the call is in Tempo under the Praxis service.
- `zuno-demo-reorg` is told before the client rolls, so its offline walkthrough suite is re-run for this client.
