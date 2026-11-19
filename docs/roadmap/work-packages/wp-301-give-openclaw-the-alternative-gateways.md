# WP-301: Give OpenClaw the alternative gateways

- **State:** Done (2026-11-19): both OpenClaw personas answer through their `praxis` provider, on Praxis's `maas` step
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

## Repo work (2026-11-19)

OpenClaw: the chart renders one custom provider per entry in each Claw and a NetworkPolicy `alt-gateways-proxy-egress` per persona to zuno-ai-gateways:8080; the role default `zuno_openclaw_alt_gateways: []` is combined into the Application values only when not empty, and the role now loads the cluster variables first. Proofs offline: `helm template` with `altGateways` empty is identical to the chart before the change (0 diff lines) and, with the Praxis entry `{name: praxis, label: Praxis, url: http://praxis.zuno-ai-gateways.svc:8080/v1, models: [auto]}`, adds only the objects above; the role's values expression renders without the key for an empty list and with `altGateways` only for a non-empty one (rendered through Ansible for both); `ansible-playbook --syntax-check` of `day2_install.yml`; `check_docs.py`. The demo333 entry in `ansible/clusters/demo333.yml` is NOT added: it comes at the live step. The proxy pod label `app: claw-proxy` was read live on 2026-11-19 (`oc get pod -A -l app=claw-proxy`: `assistant-proxy-*` in zuno-claw-consultant-02 and zuno-claw-sale-01, labels `app=claw-proxy,claw.sandbox.redhat.com/instance=assistant`), so the selector matches.

## Acceptance

- With `altGateways` empty, the rendered chart is identical to before (`helm template` diff), and the client's existing golden-path probe passes.
- With the Praxis entry, the alternative connection is listed in the client and answers a C1 question; a trace of the call is in Tempo under the Praxis service.
- `zuno-demo-reorg` is told before the client rolls, so its offline walkthrough suite is re-run for this client.

## 2026-11-19: live on demo333 (owner's go)

- **Install:** commit fbf91f6c adds the demo333 entry `zuno_openclaw_alt_gateways` (Praxis, models `[auto]`). Before
  the push, the chart was rendered with the live `zuno-openclaw-d1` values. The only additions were the two
  `alt-gateways-proxy-egress` NetworkPolicies, plus the `zuno-alt-praxis` credential and the `praxis` provider in each
  Claw. `make d2 install openclaw` was then run locally, without confidential.yml (the role only seeds missing Vault
  paths): `ok=110 failed=0`. Argo synced, and both assistants and their proxies restarted, Ready.
- **Proof:** from each assistant's `gateway` container, with no Authorization header (the claw proxy adds the
  `openclaw-<persona>` token for the `praxis.zuno-ai-gateways.svc` domain), `POST /v1/chat/completions` with model
  `auto` and a C1 question was sent to `http://praxis.zuno-ai-gateways.svc:8080/v1`:
  - **Result:** HTTP 200 from `qwen3.6-27b-instruct` for both personas (10 to 65 s).
  - **Praxis log:** `sub-request complete step="maas" status=200` for each call.
  - **Tempo:** traces `eae7c9f1…`, `9f9345e9…`, `f14d45bb…`, `facaa4b3…` under the Praxis service.
- **Default road unchanged:** the golden-path probe `openclaw` (assistant → ai-gateway) passes.
- **Note:** qwen3.6 reasons before it answers. With `max_tokens: 200`, the whole budget went into reasoning and the
  content was empty. With 2000, it used 483 to 1258 tokens for a one-sentence answer. OpenClaw's own requests carry
  larger budgets, so this is a latency cost, not a failure.
- **Rollback:** set `zuno_openclaw_alt_gateways: []`, then run `make d2 install openclaw` (both assistants restart).
