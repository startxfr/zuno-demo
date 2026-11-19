# WP-303: Give world-model the alternative gateways

- **State:** Operator pending (2026-11-19): the Praxis entry is committed and the web image rebuilt; the live proof waits for the next switch-on of world-model (owner's choice)
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

## Repo work (2026-11-19)

world-model: the web tier reads ALT_GATEWAYS and PROMPT_GATEWAY and sends the prompt enhancement through the gateway a request names; the role default `zuno_world_model_alt_gateways: []` is combined into the Application values only when not empty. Proofs offline: `helm template` with `altGateways` empty is identical to the chart before the change (0 diff lines) and, with the Praxis entry `{name: praxis, label: Praxis, url: http://praxis.zuno-ai-gateways.svc:8080/v1, models: [auto]}`, adds only the objects above; the role's values expression renders without the key for an empty list and with `altGateways` only for a non-empty one (rendered through Ansible for both); `ansible-playbook --syntax-check` of `day2_install.yml`; `check_docs.py`. The web tier's tests pass (40). The demo333 entry in `ansible/clusters/demo333.yml` is NOT added: it comes at the live step.

## Acceptance

- With `altGateways` empty, the rendered chart is identical to before (`helm template` diff), and the client's existing golden-path probe passes.
- With the Praxis entry, the alternative connection is listed in the client and answers a C1 question; a trace of the call is in Tempo under the Praxis service.
- `zuno-demo-reorg` is told before the client rolls, so its offline walkthrough suite is re-run for this client.

## 2026-11-19: prepared on demo333, proof at the next switch-on (owner's choice)

world-model is off on demo333 (`zuno_world_model_enabled: false`). Switching it on means an on-demand g7e GPU node. The
owner chose not to switch it on for this test alone.
- **Entry:** `zuno_world_model_alt_gateways` with the Praxis entry (`models: [auto]`) is in `ansible/clusters/demo333.yml`
  (29aeeba5). It renders nothing while world-model is off.
- **Image:** the web image, built alone (`make d2 build world-model` with `world_model_build_target=web`, CPU only),
  is build `world-model-web-6`, from commit 29aeeba5, which contains 01d98512. Before it, the newest web image dated
  from 2026-11-09. The GPU runtime image was not rebuilt.
- **Left for Done, at the next switch-on (for example the demo rehearsal):**
  - one prompt enhancement with `gateway: praxis` by a signed-in user;
  - a 200 on Praxis's `maas` step in its log, and the trace in Tempo;
  - the `world-model` golden-path probe still passes on the default road.
  The web tier sends the user's own world-model token to Praxis. Praxis requires the audience `zuno-admin-api`, so
  check that the token carries it at that time.
