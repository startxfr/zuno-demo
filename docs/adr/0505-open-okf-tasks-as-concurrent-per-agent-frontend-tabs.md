# ADR-0505: Open OKF tasks as concurrent per-agent frontend tabs

- **Status:** Proposed
- **Target:** OKF v0.1
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team

## Context

An OKF bundle already declares a task catalog — Tekos lists
`answer-technical-question`, `find-relevant-docs` and
`check-my-drive-docs` in `zuno.tasks` — but the UI exposes exactly one of
them: the chat page drives the agent's `zuno.primary_task` through
`POST /v1/agents/{agent}/chat`, and the other declared tasks are
reachable by no user action at all. The task files exist, carry their own
tool and knowledge ceilings (`zuno.allowed_tools`,
`zuno.allowed_knowledge`), and are validated and baked into every image —
then never invoked. `components/agent-frontend` is one shared
Go+React/PatternFly codebase deployed per agent (ADR-0008, ADR-0044), so
a task-navigation change lands once and applies to every agent.

ADR-0212 (persistent, navigable conversations) supplies the substrate a
multi-tab UI needs: a durable `run_id` per conversation, a transcript
reload endpoint, and a left-hand conversation list. What it does not add
is any notion of *which task* a conversation runs. ADR-0407 (v0.4 stub,
"add specialized task-oriented frontend views") gestures at the broader
ambition — structured, non-chat interfaces for complex workflows — but
nothing narrower exists for simply making the declared task catalog
usable. This ADR delivers that narrow slice early and leaves ADR-0407's
wider scope where it is.

## Decision

1. **Within one agent's UI, each task in `zuno.tasks` can be open
   concurrently as its own in-app tab.** A PatternFly `Tabs` bar renders
   one tab per declared task; each open tab holds its own conversation
   (its own ADR-0212 `run_id`, transcript and state), so a user can run
   `find-relevant-docs` beside a long `answer-technical-question` thread
   without either losing context. `zuno.primary_task` is the default tab
   on first load. In-app tabs and ADR-0212's browser-tab handling
   (`tabTracker.ts`) compose: a conversation link still opens/focuses the
   agent's browser tab, then activates the in-app tab for that
   conversation's task.

2. **The tab bar is OKF-driven, end to end.** Tab identity, order and
   default come from `zuno.tasks` and `zuno.primary_task`; label and icon
   come from a small optional per-task UI block added to the task
   frontmatter schema (`zuno.ui.tabLabel`, `zuno.ui.icon` — defaulting to
   the task title). No task list is ever hardcoded in the frontend; a
   bundle change is the only way tabs change.

3. **Tabs are entitlement-filtered before render.** A task tab renders
   only when the caller's validated business-role groups (ADR-0040)
   intersect non-emptily with the `allowed_groups` of at least one of the
   task's declared tools or knowledge domains — the same policy-file
   sources the ADR-0503 matrix reads. A task whose every resource the
   user cannot reach is not shown disabled; it is not shown. A
   `project_required` task (ADR-0512) renders its tab, but the tab's
   conversation cannot start before project binding succeeds.

4. **The chat contract gains an explicit task parameter.** `POST
   /v1/agents/{agent}/chat` (BFF and Agent Runtime, OpenAPI-first per
   ADR-0054) accepts an optional `task`; absent means `primary_task`
   (today's behavior, bit-for-bit). Agent Runtime validates `task ∈
   zuno.tasks`, executes the named task's graph with *that task's*
   tool/knowledge ceilings — the per-task ceilings finally differ in
   effect, not just in declaration — and rejects unknown tasks fail-closed.
   The conversation row (ADR-0212) records the task, so reopening a
   conversation restores it into the right tab.

## Consequences

The declared task catalog becomes the navigation model: authoring a task
in OKF is now a user-visible act, which raises the value of the ADR-0503
matrix and the ADR-0504 contract tests that keep task declarations
honest. Agent Runtime's dispatch grows task selection on the existing
route rather than new per-task routes. WP-47 implements this ADR;
ADR-0407 keeps the structured-view ambition for v0.4 with a pointer to
this record.

## Security considerations

Task selection must not widen authorization: the effective intersection
(ADR-0011/ADR-0036) is computed per task already; the new parameter only
selects *which* declared ceiling applies, and the gateway-side
enforcement path is unchanged. Entitlement filtering of tabs is a UX
courtesy, never the enforcement point — a hand-crafted request naming a
task the user cannot exploit still meets the same server-side
intersection and fails closed. The `task` parameter is validated against
the bundle allowlist, never used as a path or file reference.

## Operational considerations

Tab metadata rides the existing bundle-baking path — no new config
channel. Frontend telemetry gains the active task as a dimension beside
agent and `run_id`, mirroring ADR-0203's tracing posture. The OpenAPI
contract change follows ADR-0054's spec-first flow, and the schema
addition (`zuno.ui` task block) lands in `platform/okf/schema/` with
validator coverage before any frontend code reads it.

## Acceptance criteria

- A Tekos consultant sees three tabs, opens two concurrently, and each
  holds an independent conversation restored correctly after reload.
- Absent `task` behaves exactly as today (primary task); an undeclared
  task name is rejected fail-closed at Agent Runtime.
- A user whose groups reach none of a task's resources never sees its
  tab, and a forged request for it still fails server-side.
- Frontend tests cover tab rendering from a bundle fixture, entitlement
  filtering, and per-tab conversation isolation.

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0008](0008-use-one-frontend-and-one-bff-deployment-per-agent.md)
- [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md)
- [ADR-0044](0044-use-patternfly-react-for-the-agent-frontend.md)
- [ADR-0054](0054-define-the-bff-contract-openapi-first.md)
- [ADR-0212](0212-introduce-persistent-navigable-chat-conversations.md)
- [ADR-0342](0342-support-multiple-agent-graph-shapes-in-agent-runtime.md)
- [ADR-0407](0400-v0.4-roadmap.md#adr-0407-add-specialized-task-oriented-frontend-views) (this ADR delivers its per-agent task-tab portion early)
- [ADR-0503](0503-make-each-okf-bundle-state-its-complete-authorization-contract.md)
- [ADR-0512](0512-introduce-project-bound-tasks-with-salesforce-verified-context.md)
