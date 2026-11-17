# WP-304: Write the multi-gateway, Claude Code and agents scenarios

- **State:** Not started
- **ADRs:** [ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)
- **Depends on:** [WP-296](wp-296-give-open-webui-the-alternative-gateways.md), [WP-297](wp-297-give-kagent-the-alternative-gateways-through-the-token-proxy.md), [WP-298](wp-298-run-claude-code-on-sovereign-models-through-praxis.md)
- **Related:** [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)
- **Target:** v0.17
- **Estimated files touched:** ~20: three pages, three `ansible/demos/<id>/` trees, the catalogue

## Goal

Three catalogue scenarios:
- `multi-gateway`: Open WebUI and kagent in 5 minutes; every wired client in 15 minutes;
- `claude-code-sovereign`;
- `agents-alt-gateway`.

## Steps

1. Pages from `docs/demo/_template-scenario.md`:
   - `docs/demo/scenarios/governance/multi-gateway.md`;
   - `docs/demo/scenarios/experiences/claude-code-sovereign.md`;
   - `docs/demo/scenarios/governance/agents-alt-gateway.md`.
2. Engine files in `ansible/demos/<id>/`, and rows in `docs/demo/README.md`.
3. Each page's limits name what the alternative gateway does not enforce:
   - persona quotas;
   - classification floors;
   - per-agent policy;
   - only C1 content is shown.
4. GIFs later, by `zuno-demo-reorg`'s chain, with the owner's go per take. `platform/demo` and `evaluations/browser` are not changed here.

## Acceptance

- `platform/demo/tests/test_page_shape.py` passes.
- `python3 platform/demo/consistency.py` reports 0 problems.
- Each scenario is played once live with the owner's go.
