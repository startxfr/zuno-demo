# WP-199: Personal UnifAI starters for the demo personas

- **State:** Repo work in review (2026-11-04: starters Ready on demo333; browser check pending)
- **ADRs:** [ADR-0598](../../adr/0598-give-every-persona-default-unifai-team-workspaces-and-a-shared-catalog.md)
- **Depends on:** WP-197, WP-198
- **Related:** [WP-175](wp-175-a2a-gateway-and-persona-test-blueprints.md) (test blueprints, unchanged)
- **Target:** v0.13
- **Estimated files touched:** ~4 (the unifai chart, demo333.yml, docs)

> Why: a persona's personal workspace stays empty even once the teams exist. User decision of 2026-11-04: declarative
> starters for consultant-01, sale-01 and ai-ops-01 only.

## Goal

consultant-01, sale-01 and ai-ops-01 each find one or two starter workflows in their personal workspace.

## Steps

1. Chart `personalStarters: [<username>]`: for each user, the agent `<username>-assistant` and the workflow
   `<username>-my-assistant`, both with `owner: <username>` and no `teamRef`, on the built-in gateway. The username is
   `preferred_username` (`consultant-01`). Like the team examples, this needs the gateway LLM and MCP provider to be
   built-ins (WP-197, UnifAI 0.1.58).
2. demo333 lists the three personas.
3. **Personal RAG** (amended 2026-11-05). The live check showed that a team workflow runs as the team and never sees a
   member's personal uploads. Each persona therefore also gets the retriever `<username>-documents` (its own uploads plus
   its groups' Confluence, forwarded token), the agent `<username>-rag` and the workflow `<username>-my-documents`.

## Acceptance

- In the personal workspace of each of the three personas, the starter is listed and answers.
- `<username>-my-documents` answers from a document the persona uploaded in Personal.
