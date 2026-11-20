# WP-304: Write the multi-gateway, Claude Code and agents scenarios

- **State:** Done (2026-11-20): the three pages exist and each scenario was played live once with the owner's go (`claude-code-sovereign` on 2026-11-18, `multi-gateway` and `agents-alt-gateway` on 2026-11-20)
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

## 2026-11-19: claude-code-sovereign rewritten from the rehearsal, GIF published

- The `claude-code-sovereign` page was rewritten from the 5-minute rehearsal of 2026-11-18 on the owner's workstation
  (ai-dev-01, `qwen3.6-27b-instruct`, the tests pass; the optional trace row was not run) and its GIF was published
  (75b05ec9). The 15-minute version is not rehearsed.
- `multi-gateway` and `agents-alt-gateway` keep the status "Not rehearsed": their pages were not updated for the
  Praxis deployment that landed under WP-292 and WP-298.
- State moved from Not started to Operator pending: the repository work of the step list is done, what remains needs
  the owner's go and live plays. "In progress" is not a state of the tracker.

## 2026-11-20: multi-gateway and agents-alt-gateway played live

Owner's go of 2026-11-20 (evening). `make demo rehearse <id> 15` passes for both pages (their status and read steps). The chat
steps, which a rehearsal does not run, were played through the clients' own APIs with the pages' personas (22:18-22:25 UTC):

- **multi-gateway, Open WebUI as ai-ops-01:** the model list shows `Zuno`, `Zuno Code`, `Zuno wesh`, then the
  `praxis.`-prefixed models (`praxis.auto`, the four local models, `praxis.claude`, `praxis.codestral-latest`). The 0:45
  question on `Zuno` is answered in 1 s; the same question on `praxis.auto` is answered in 50 s. The Praxis log shows the
  `maas` step at 200. The time is qwen3.6's reasoning before it answers (WP-301 note): on stage, ask the Praxis
  question first, or say that the local model thinks before it answers.
- **multi-gateway and agents-alt-gateway, kagent:** the 2:15 / 1:30 question to `zuno-sre` is answered in 1.5 s on the
  default road; to `zuno-diagnose-praxis` in 11 s through Praxis (`maas` step, 200). No tool call on either.
- **agents-alt-gateway, Dify (2:30, 3:15):** not replayed tonight; the `praxis-auto` model rests on WP-300's live proof
  of 2026-11-19.
