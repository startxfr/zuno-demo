# WP-198: Default UnifAI team workspaces, shared inventory and catalog

- **State:** Repo work in review
- **ADRs:** [ADR-0598](../../adr/0598-give-every-persona-default-unifai-team-workspaces-and-a-shared-catalog.md), [ADR-0597](../../adr/0597-declare-unifai-built-in-resources-through-the-operator.md)
- **Depends on:** WP-197 (steps 3 and 4 only)
- **Related:** [WP-199](wp-199-personal-unifai-starters-for-the-demo-personas.md), [WP-201](wp-201-rewire-the-unifai-devel-sandbox-onto-the-gateway.md)
- **Target:** v0.13
- **Estimated files touched:** ~6 (the unifai chart values, objects and helpers, demo333.yml, docs)

> Why: consultant-01 found no team, no inventory and no workflow in UnifAI (2026-11-04). User decisions of 2026-11-04:
> target `zuno-unifai`; business teams next to the agent teams (consultant, sales, adv, finance, board, recrut, cdp, ops);
> zuno templates without keys; example workflows per team; the five Pending bundles are out of scope.

## Goal

A persona logs into `unifai-ui-zuno-unifai` and finds its business team and its agent teams, a catalog that works without
any key, the shared gateway in "Built-in", and example workflows in its team.

## Steps

1. **Teams.** Chart `teams:` list rendering UnifaiTeam objects with group members, owner `$owner`. demo333 declares the
   eight teams.
2. **Templates.** Chart `templates.enabled`: `zuno-chat`, `zuno-tools-agent` and `zuno-draft-review` on the gateway LLM
   and MCP config, shared with the objects through `_helpers.tpl`.
3. **Shared inventory (after WP-197).** `gatewayLLM.builtin` and `mcpGateway.builtin` set to true on demo333.
4. **Team workflows (after WP-197).** Chart `teamExamples.enabled` plus `examples: true` on a team entry: in that team's
   inventory, the agents `<team>-assistant` and `<team>-tools` (MCP), the condition `<team>-direct` (router_direct) and
   the agent `<team>-orchestrator`. Three workflows run on them: `<team>-linear`, `<team>-branches` and
   `<team>-orchestrated`. The chart fails if the gateway LLM and MCP provider are not both built-ins. The RAG example
   moves to WP-200: no retriever is reachable from a business team (built-in retrievers are refused, and the
   `knowledge-*` retrievers belong to the agent teams). On demo333: `examples: true` for every team with personas
   (all but cdp).

## Acceptance

- `helm template` with the demo333 values adds only the new objects (no change to the existing ones), and
  `oc apply --dry-run=server` admits them.
- Live: `oc get unifaiteam -n zuno-unifai` shows the eight business teams and the three agent teams, all Ready.
- As consultant-01 (browser), the team selector lists consultant, agent-tekos, agent-arkos and agent-comage, but not sales.
  "Zuno Chat" generates a workflow that answers.
- As sale-01: sales and agent-comage only.
