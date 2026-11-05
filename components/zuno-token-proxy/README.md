# zuno-token-proxy

ADR-0601. An experience client that cannot forward its user's Keycloak token
(Dify, ADR-0599; kagent, ADR-0600) reaches the ai-gateway and the mcp-gateway
through this proxy, deployed in its own namespace by
`gitops/charts/zuno-token-proxy`.

| Path | Upstream |
|---|---|
| `/v1/...` | ai-gateway `/v1/...` (chat completions, models; streaming passthrough) |
| `/mcp`, `/mcp/...` | mcp-gateway `/mcp...` (streamable HTTP, SSE, `mcp-session-id` kept) |
| `/healthz`, `/readyz`, `/metrics` | local (`/readyz` is 503 while no valid token is held) |

- **Token.** `client_credentials` against the Keycloak Route, cached, refreshed at
  `REFRESH_RATIO` (0.7) of its lifetime. A failed refresh keeps the current token
  while it is valid; with none, every relayed call is `503` and nothing is sent.
- **Headers.** The client's `Authorization` (a dummy key) is dropped. `AI_HEADERS` and
  `MCP_HEADERS` (JSON objects) replace any header of the same name.
- **Metrics.** `zuno_token_proxy_refresh_total{result}`,
  `zuno_token_proxy_requests_total{upstream,code}`.

| Env | Meaning |
|---|---|
| `TOKEN_URL`, `CLIENT_ID`, `CLIENT_SECRET` or `CLIENT_SECRET_FILE` | Keycloak client of the experience (required) |
| `AI_GATEWAY_URL`, `MCP_GATEWAY_URL` | upstreams (default the `zuno-ai-run` services) |
| `AI_HEADERS`, `MCP_HEADERS` | fixed headers, e.g. `{"X-Zuno-Agent": "dify", "X-Zuno-Task": "chat"}` |
| `TOKEN_SCOPE`, `REFRESH_RATIO`, `UPSTREAM_TIMEOUT_S`, `TOKEN_TIMEOUT_S`, `CA_BUNDLE` | optional |

Tests (Keycloak and both gateways faked, clock injected):

    cd components/zuno-token-proxy && python3 tests/test_token_proxy.py

Build: `make d2 build token-proxy` (`ansible/roles/token_proxy_build`).
