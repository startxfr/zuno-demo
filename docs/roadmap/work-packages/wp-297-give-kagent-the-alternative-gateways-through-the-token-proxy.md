# WP-297: Give kagent the alternative gateways through the token proxy

- **State:** Done (2026-11-19): kagent's `zuno-diagnose-praxis` agent answers through its token proxy's `/alt/praxis` route on Praxis, live on demo333; the default `zuno-sre`/`zuno-diagnose` path and Dify are unchanged
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

## 2026-11-19: the list reaches kagent (repo)

The code of steps 1 to 3 has been on devel since c4a6cdd8 (2026-11-17), but no variable handed the list to kagent's
two Applications. The kagent role now has `zuno_kagent_alt_gateways` (default `[]`). It passes the list as
`altGateways` to `zuno-token-proxy-kagent-d1` (the proxy's `ALT_GATEWAYS` and its egress rule to
`zuno-ai-gateways:8080`) and to `zuno-kagent-d1` (one `ModelConfig zuno-model-<name>` on
`http://zuno-token-proxy:8080/alt/<name>/v1` and one `Agent zuno-diagnose-<name>`). The pattern is the one of Dify,
WP-300.
- **An empty list** adds nothing: the values are the ones of before.
- **On demo333**, the list holds the Praxis entry with the local alias `auto` only, because kagent's agents always
  carry tools, which Praxis refuses on its SaaS models.
- **Checked:**
  - with the live values, `helm template` of kagent adds exactly the Agent and the ModelConfig;
  - the token proxy adds the env and the egress rule;
  - the token-proxy tests pass (48);
  - the playbook syntax and `check_docs.py` pass.
- **Not set:** the proxy's CA bundle. That is harmless for Praxis, which is in-cluster http.
- `load_cluster_vars` was already in the role (78b1bafc).

## 2026-11-19: live on demo333 (owner's go)

- **Rebuild:** `make d2 build token-proxy` rebuilt `zuno-ai-build/zuno-token-proxy:latest` from devel. The last build,
  of 11-15, predated the WP-297 code. Both proxies, `zuno-kagent` and `zuno-dify`, rolled on the new image
  (08:49Z).
- **Install:** `make d2 install kagent` (local run, `ok=105 failed=0`). `zuno-token-proxy-kagent-d1` and
  `zuno-kagent-d1` are Synced and Healthy. The proxy carries `ALT_GATEWAYS`. `ModelConfig zuno-model-praxis` (model
  `auto`, base URL `http://zuno-token-proxy:8080/alt/praxis/v1`) and `Agent zuno-diagnose-praxis` (Ready, Accepted)
  exist.
- **The route,** called from inside the kagent proxy pod:
  - `GET /alt/praxis/v1/models` returns 200 with `auto, qwen3.6-27b-instruct, gpt-oss-20b, qwen3.5-9b`;
  - a chat on `auto` returns 200 "pong".
- **The agent:** an A2A `message/send` to `zuno-diagnose-praxis` (kagent controller) asked "which pods in namespace
  zuno-kagent are not Running?" and completed with an answer from the live namespace. Praxis's log shows its model
  calls on the `maas` step with 200 (08:54:45Z, 08:54:56Z, 08:55:01Z).
- **Unchanged:** the golden-path probes `kagent` and `dify` pass on the default road (the ai-gateway, `gpt-oss-20b`).
- **Notices:** zuno-demo-cluster and zuno-demo-assist were told before the roll; zuno-demo-reorg is closed.
- **Rollback:** set `zuno_kagent_alt_gateways: []` and rerun `make d2 install kagent`.

