# WP-296: Give Open WebUI the alternative gateways

- **State:** Done (2026-11-17: live on demo333, Praxis listed next to "Zuno" and answering)
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

## Result (2026-11-17)

The repo work (the `altGateways` list, the `OPENAI_API_CONFIGS` index, the egress rule) was delegated and is on devel. The live steps ran with the owner's go of 2026-11-17, after the heads-up to `zuno-demo-reorg`; its offline walkthrough suite for Open WebUI passed.

- **Setting:** `open_webui_alt_gateways` in `ansible/clusters/demo333.yml` holds one entry, `praxis` (`8f63b23d`).
- **Finding:** the first install applied the Application unchanged. The role never loaded `ansible/clusters/<cluster>.yml`, so its empty default won. The role now includes `load_cluster_vars.yml` (`1c5c9017`). kagent and Dify have the same gap; OpenClaw loads the file in `vault.yml` only. Their own WPs fix it before setting their lists.
- **Roll:** `zuno-open-webui-d1` is Synced and Healthy at `1c5c9017`. The pod restarted once with:
  - `OPENAI_API_BASE_URLS` = the ai-gateway, then Praxis;
  - index 1 of `OPENAI_API_CONFIGS`: `system_oauth`, `prefix_id` `praxis`, tag "Praxis".
- **As the persona `eval-consultant-01`,** signed in through Keycloak:
  - `/api/models` lists `auto` and `zuno-code`, then `praxis.auto`, `praxis.qwen3.6-27b-instruct`, `praxis.gpt-oss-20b`, `praxis.qwen3.5-9b`, `praxis.qwen3.5-9b-wesh`, `praxis.claude` and `praxis.codestral-latest`, all tagged "Praxis";
  - `praxis.gpt-oss-20b` and `praxis.auto` (served by `qwen3.6-27b-instruct`) answer a C1 question.
- **Zuno default unchanged:** `golden_path_probe.py --only open-webui,zuno-code` passes (`auto` and `zuno-code` through the ai-gateway).
- **Trace:** Tempo holds Praxis traces of `/v1/chat/completions` calls with `user_agent.original` "Python/3.12 aiohttp/3.14.5", the HTTP client Open WebUI uses; 20 in 10 minutes. `client.address` is the sidecar's `127.0.0.6`, not the Open WebUI pod.
- **Not done:** a scout of the live model picker for the GIF walkthrough. Its selector matches "Zuno Code" exactly, and no Praxis entry has that name. A scout is the owner's decision in demo333's session.

## 2026-11-19: no Zuno tools on the SaaS models of Praxis

`praxis.claude` and `praxis.codestral-latest` got a 403 `saas_tools_not_allowed` until the user turned the tools off
in the chat, because the chart's `DEFAULT_MODEL_METADATA` attaches the Zuno tools to every model (ADR-0619, update of
2026-11-18). The role now writes a per-model entry with no tools for these two models
(`ansible/roles/open_webui/files/model_overrides.py`, ids from the Praxis chart's SaaS names, tested by
`platform/praxis/tests/test_open_webui_no_tools.py`). The local `praxis.*` models keep the tools. Applied by `make
d2 install open-webui` (ADR-0619, update of 2026-11-19).

