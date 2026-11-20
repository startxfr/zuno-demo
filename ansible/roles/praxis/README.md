# praxis

Praxis AI as an alternative AI gateway next to the Zuno ai-gateway
([ADR-0619](../../../docs/adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md),
[WP-292](../../../docs/roadmap/work-packages/wp-292-deploy-praxis-ai-in-the-alternative-gateways-namespace.md)). Day 2,
`make d2 install|check|uninstall praxis`.

It follows one switch, `zuno_praxis_enabled` (default `false`, set in `ansible/inventories/<cluster>/cluster.yml`):

- **Off:** the Applications `zuno-praxis-d0` and `zuno-praxis-d1` are removed if they exist, and nothing else happens.
- **On:** the role needs `zuno_praxis_image_digest` (the digest `make d2 build praxis` prints, WP-291), applies the
  Applications with the cluster values and waits for the Deployment.

| Variable | Default | Meaning |
|---|---|---|
| `zuno_praxis_enabled` | `false` | the switch; the models and redis roles read it too (they admit the Praxis pod) |
| `zuno_praxis_image_digest` | `""` | `sha256:<64 hex>` of `quay.io/zuno/praxis-ai` |
| `zuno_praxis_saas_enabled` | `false` | Claude and Codestral, with their Vault keys |
| `zuno_praxis_token_rate_limit_enabled` | `false` | per-subject token limit on Redis: our build only |
| `zuno_praxis_otel_enabled` | `false` | OpenTelemetry spans: our build only |
| `zuno_praxis_workstation_entry` | `false` | admit the zuno-agent-gateway proxy (with connectivity-link `praxisWorkstationEntry`) |

Turn it on in this order: the allow-lists first (`make d2 install models`, `make d1 install redis`: they admit the
pod and subscribe its ServiceAccount to the models), then `make d2 install praxis`. `make d2 check praxis` proves the
Deployment, the metrics port and the 401 without a token.

The chart is `gitops/charts/praxis`; the namespace, its mesh labels and its egress firewall are in
`gitops/charts/namespaces`.
