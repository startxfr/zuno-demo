# WP-199: Personal UnifAI starters for the demo personas

- **State:** Not started
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

1. Chart `personalStarters: [{username, workflows}]` rendering UnifaiWorkflow objects with `owner: <username>`, no
   `teamRef`, on the built-in gateway. The username is `preferred_username` (`consultant-01`).
2. demo333 lists the three personas.

## Acceptance

- In the personal workspace of each of the three personas, the starter is listed and answers.
