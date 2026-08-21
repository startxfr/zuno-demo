# ADR-0505: Open OKF tasks as concurrent per-agent frontend tabs

- **Status:** Superseded by ADR-0515 (Abandoned before implementation)
- **Target:** OKF v0.1
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team
- **Superseded:** 2026-08-21 by [ADR-0515](0515-per-conversation-tabs-one-browser-tab-per-agent.md)

## Historical context

An OKF bundle already declared a task catalog — Tekos listed
`answer-technical-question`, `find-relevant-docs` and
`check-my-drive-docs` in `zuno.tasks` — but the UI exposed exactly one of
them: the chat page drove the agent's `zuno.primary_task` through
`POST /v1/agents/{agent}/chat`, and the other declared tasks were
reachable by no user action at all. `components/agent-frontend` is one
shared Go+React/PatternFly codebase deployed per agent (ADR-0008,
ADR-0044), so a task-navigation change was meant to land once and apply
to every agent. ADR-0212 (persistent, navigable conversations) supplied
the substrate — a durable `run_id` per conversation, a transcript reload
endpoint, a left-hand conversation list, and `tabTracker.ts`'s
browser-tab-per-conversation focusing — that this decision built on.

## Historical decision

This ADR decided to expose each declared task as its own concurrent
in-app tab: a PatternFly `Tabs` bar with one tab per `zuno.tasks` entry,
`zuno.primary_task` as the default, tabs entitlement-filtered per row,
tab label/icon sourced from a new `zuno.ui` frontmatter block, and an
explicit `task` parameter added to the chat contract.

WP-47 never started — no code was written against this decision. Before
implementation began, the design was reconsidered: tying tab identity to
*task* conflated two different things a user actually wants — which
conversation they are in, and which task that conversation runs.
[ADR-0515](0515-per-conversation-tabs-one-browser-tab-per-agent.md)
replaces this decision with tabs keyed by *conversation*, one browser tab
per agent instead of one per conversation, and folds task selection
inside a conversation rather than into tab identity. ADR-0512's
`project_required` gating and the ADR-0503 authorization matrix are
unaffected in substance — only the UI surface that exposes them changes.

See [Standard clauses](README.md#standard-clauses) for Context,
Alternatives, Consequences, Security/Operational considerations,
Migration/evolution and Related ADRs.

## Related ADRs

- [ADR-0008](0008-use-one-frontend-and-one-bff-deployment-per-agent.md)
- [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md)
- [ADR-0044](0044-use-patternfly-react-for-the-agent-frontend.md)
- [ADR-0054](0054-define-the-bff-contract-openapi-first.md)
- [ADR-0212](0212-introduce-persistent-navigable-chat-conversations.md)
- [ADR-0342](0342-support-multiple-agent-graph-shapes-in-agent-runtime.md)
- [ADR-0407](0400-v0.4-roadmap.md#adr-0407-add-specialized-task-oriented-frontend-views) (this ADR was meant to deliver its per-agent task-tab portion early; ADR-0515 does so instead)
- [ADR-0503](0503-make-each-okf-bundle-state-its-complete-authorization-contract.md)
- [ADR-0512](0512-introduce-project-bound-tasks-with-salesforce-verified-context.md)
- [ADR-0515](0515-per-conversation-tabs-one-browser-tab-per-agent.md) (supersedes this ADR)
