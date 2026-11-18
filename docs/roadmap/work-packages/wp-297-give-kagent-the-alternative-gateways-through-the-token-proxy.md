# WP-297: Give kagent the alternative gateways through the token proxy

- **State:** Not started
- **ADRs:** [ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)
- **Depends on:** [WP-292](wp-292-deploy-praxis-ai-in-the-alternative-gateways-namespace.md)
- **Related:** [ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)
- **Target:** v0.17
- **Estimated files touched:** ~10: zuno-token-proxy app, tests and chart; the kagent chart

## Goal

A kagent agent can run on an alternative gateway. zuno-token-proxy gets generic alternate upstreams, which Dify (WP-300) reuses.

## Steps

1. zuno-token-proxy (`components/zuno-token-proxy/app/config.py`, `main.py`):
   - an `ALT_GATEWAYS` env (JSON: name, url, headers);
   - routes `/alt/<name>/v1/{path}` relayed by the existing `relay()`;
   - `verify=` set to the CA bundle for HTTPS upstreams;
   - timeouts by route;
   - tests.
2. Its chart: the env from `altGateways`, and egress to `zuno-ai-gateways:8080`.
3. kagent chart: one `ModelConfig` per entry (base URL `<proxy>/alt/<name>/v1`), plus a demo Agent `zuno-diagnose-<name>`.
4. Live, with the owner's go: rebuild and roll the token-proxy, then kagent.

## Acceptance

- With `altGateways` empty, the rendered chart is identical to before (`helm template` diff), and the client's existing golden-path probe passes.
- With the Praxis entry, the alternative connection is listed in the client and answers a C1 question; a trace of the call is in Tempo under the Praxis service.
- `zuno-demo-reorg` is told before the client rolls, so its offline walkthrough suite is re-run for this client.
- `components/zuno-token-proxy` tests pass in CI.
