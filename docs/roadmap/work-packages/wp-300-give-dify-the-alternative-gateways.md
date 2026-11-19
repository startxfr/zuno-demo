# WP-300: Give Dify the alternative gateways

- **State:** Done (2026-11-19): Dify has a model `praxis-auto` on its token proxy's `/alt/praxis` route, live on demo333; the default Dify path is unchanged
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

## 2026-11-19: live on demo333 (owner's go)

- **Code:** the repo work (configure.py, the role's `zuno_dify_alt_gateways`, the token proxy's alternate route) was
  already on devel (092316c47 and WP-297). 95962154 adds the demo333 entry: Praxis, models `[auto]`, the local alias
  only, because Dify's agent app carries the Zuno tools, which Praxis refuses on its SaaS models.
- **Install:** zuno-demo-cluster ran `make d2 install dify` from a throwaway worktree at 02de0c68, with
  confidential.yml. The role needs the `zuno_dify_s3_*` values, which neither a scratch worktree nor AAP has
  (AAP job 1476 stopped before any change). Result: `ok=157 failed=0`, "model: praxis-auto registered".
  `zuno-token-proxy-dify-d1` and `zuno-dify-d1` are Synced and Healthy. The Dify proxy rolled once and carries
  `ALT_GATEWAYS`.
- **The call:** registering the model makes Dify call it. Praxis's log shows that call on the `maas` step with 200
  (09:41:41Z), through the Dify proxy's alternate route.
- **Unchanged:** the golden-path probe `dify` passes on the default road (ai-gateway, `gpt-oss-20b`).
- **To try in the UI:** in Dify, set the model of an app to `praxis-auto`.
- **Rollback:** set `zuno_dify_alt_gateways: []`, run `make d2 install dify`, and remove the model in Dify.
- **Gap left:** AAP lacks the Dify S3 values, so `make d2 install dify` cannot run through AAP.

