# WP-301: Give OpenClaw the alternative gateways

- **State:** Repo work merged (2026-11-19): the chart renders one custom provider per entry in each Claw and a NetworkPolicy `alt-gateways-proxy-egress` per persona to zuno-ai-gateways:8080; the role default `zuno_openclaw_alt_gateways: []` is combined into the Application values only when not empty, and the role now loads the cluster variables first. The live steps wait for the owner's go
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
