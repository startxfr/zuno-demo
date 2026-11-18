# zuno-token-proxy

ADR-0601. An experience client that cannot forward its user's Keycloak token
(Dify, ADR-0599; kagent, ADR-0600) reaches the ai-gateway and the mcp-gateway
through this proxy, deployed in its own namespace by
`gitops/charts/zuno-token-proxy`.

| Path | Upstream |
|---|---|
| `/v1/...` | ai-gateway `/v1/...` (chat completions, models; streaming passthrough) |
| `/mcp`, `/mcp/...` | mcp-gateway `/mcp...` (streamable HTTP, SSE, `mcp-session-id` kept) |
| `/alt/<name>/v1/...` | the alternative gateway `<name>` of `ALT_GATEWAYS`: `<its url>/...` (WP-297, ADR-0619 clause 5) |
| `/healthz`, `/readyz`, `/metrics` | local (`/readyz` is 503 while no valid token is held) |

- **Token.** `client_credentials` against the Keycloak Route, cached, refreshed at
  `REFRESH_RATIO` (0.7) of its lifetime. A failed refresh keeps the current token
  while it is valid; with none, every relayed call is `503` and nothing is sent.
- **Headers.** The client's `Authorization` (a dummy key) is dropped. `AI_HEADERS` and
  `MCP_HEADERS` (JSON objects) replace any header of the same name.
- **Callers (WP-225 lot C).** With `INBOUND_KEYS_FILE` (one key per line, at least 24
  characters), a request must carry `Authorization: Bearer <key>`; anything else is `401`
  and nothing is fetched or relayed. Unset: no inbound check (NetworkPolicy only).
- **Alternative gateways (WP-297).** `ALT_GATEWAYS` is a JSON list of `{name, url, headers?, timeout_s?}`;
  `url` is the gateway's OpenAI base URL (it ends with `/v1`). `/alt/<name>/v1/<path>` is relayed to
  `<url>/<path>` with that entry's fixed headers, the same token and the same caller check; an unknown
  name is `404` and nothing is relayed. An HTTPS gateway is verified against `CA_BUNDLE`. Unset or empty:
  no such route exists and the proxy behaves as before.
- **Metrics.** `zuno_token_proxy_refresh_total{result}`,
  `zuno_token_proxy_requests_total{upstream,code}`.

| Env | Meaning |
|---|---|
| `TOKEN_URL`, `CLIENT_ID`, `CLIENT_SECRET` or `CLIENT_SECRET_FILE` | Keycloak client of the experience (required) |
| `AI_GATEWAY_URL`, `MCP_GATEWAY_URL` | upstreams (default the `zuno-ai-run` services) |
| `AI_HEADERS`, `MCP_HEADERS` | fixed headers, e.g. `{"X-Zuno-Agent": "dify", "X-Zuno-Task": "chat"}` |
| `TOKEN_SCOPE`, `REFRESH_RATIO`, `UPSTREAM_TIMEOUT_S`, `TOKEN_TIMEOUT_S`, `CA_BUNDLE` | optional |
| `INBOUND_KEYS_FILE` | optional (WP-225 lot C): the keys a caller must present |
| `ALT_GATEWAYS` | optional (WP-297): the alternative gateways, e.g. `[{"name": "praxis", "url": "http://praxis.zuno-ai-gateways.svc:8080/v1"}]` |

Tests (Keycloak and both gateways faked, clock injected):

    cd components/zuno-token-proxy && python3 tests/test_token_proxy.py
    cd components/zuno-token-proxy && python3 tests/test_wp297_alt_gateways.py

Build: `make d2 build token-proxy` (`ansible/roles/token_proxy_build`).
