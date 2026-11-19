# WP-299: Give UnifAI the alternative gateways

- **State:** Done (2026-11-19): a C1 chat through `zuno-gateway-praxis` answered for consultant-01, served on Praxis's `maas` step
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

## 2026-11-19: live on demo333 (owner's go)

- **Install:** zuno-demo-cluster ran `make d2 install unifai` from a throwaway worktree at 8ac303a9 (with 02de0c68,
  the demo333 entry: Praxis, models `[auto]`), with confidential.yml, because the role reads it for the backup
  values. Result: `ok=69 failed=0`.
- **What is live:**
  - `UnifaiLLM zuno-gateway-praxis` is Ready: `openai_compatible`, `base_url
    http://praxis.zuno-ai-gateways.svc:8080/v1`, `model_name auto`, `forward_user_token: true`.
  - The UnifaiStack is Ready, with `.zuno-ai-gateways.svc` in `outboundAllowedHosts`.
  - multiagent-be and the temporal worker rolled once. The backend and the UI did not. The 8 bundles are unchanged.
- **Checks:**
  - From the multiagent pod, `GET http://praxis.zuno-ai-gateways.svc:8080/v1/models` without a token gets 401: the
    network path is open and Praxis enforces its token.
  - The golden-path probe `unifai-tekos` passes (the default road, `gpt-oss-20b` through MaaS at C2).
- **Left for Done:** one C1 chat through `zuno-gateway-praxis` by a signed-in user, with a 200 on Praxis's `maas`
  step in its log. The LLM is a shared one that a workflow chooses. No catalogue workflow uses it yet, so the test
  goes through the UnifAI UI.
- **Rollback:** set `zuno_unifai_alt_gateways: []` and run `make d2 install unifai` (one more multiagent roll).

## 2026-11-19: Done, the C1 chat

The operator test was run by zuno-demo through the API, at the owner's choice, instead of in the UI. It uses the
same UI route and the same Keycloak form sign-in as a browser, through `evaluations/common/unifai_target.py`.

- **Workflow:** a throwaway blueprint in consultant-01's personal space, `wp299-praxis-c1-probe`. It has a question
  node, one agent on `$ref:ec25af21…` (the rid of `zuno-gateway-praxis`), and a final answer. It was deleted after the
  run, with its session.
- **Question (C1):** "In two sentences: what is the difference between a Kubernetes Deployment and a StatefulSet?"
- **Result:** HTTP 200 and a correct two-sentence answer, 234 s end to end.
- **Praxis log:** two `/v1/chat/completions` calls. Both were admitted by the `per-user` token rate limit, and both
  ended with `sub-request complete step="maas" status=200`.
- **Tempo:** trace `b4d4069e1012b702deb1a9d201d8a1bf` (`mas.run.id` 325cb417…) is one trace for the whole path:
  `unifai-multiagent-temporal-worker` (`chat auto`), then `praxis` (`token_rate_limit`,
  `filtered_subrequest step=maas`), then `maas.openshift-ingress`, then `qwen36-27b-instruct-kserve`.
- **Finding, not a blocker:** the first model call took 213 s and streamed 1 MB, likely a long reasoning phase of
  qwen3.6 behind `auto`. UnifAI's LLM client gave up at 200 s: the worker's sidecar span ends with status 0. UnifAI
  then retried, and the retry answered in 33 s. A workflow on this LLM can therefore take 3 to 4 minutes on a first
  turn. Before Praxis is shown in UnifAI at the demo, check it again, or cap or disable qwen3.6's thinking on the
  Praxis route.
