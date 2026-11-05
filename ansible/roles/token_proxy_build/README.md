# token_proxy_build

Day 2 build component `token-proxy` (`make d2 build token-proxy`): builds
`components/zuno-token-proxy` (ADR-0601) into `zuno-ai-build/zuno-token-proxy`
and lets the `zuno-token-proxy` ServiceAccount of each namespace in
`zuno_token_proxy_namespaces` pull it. The proxy is deployed per experience
client by `gitops/charts/zuno-token-proxy`, one Application per client
(WP-204 for Dify, WP-207 for kagent).
