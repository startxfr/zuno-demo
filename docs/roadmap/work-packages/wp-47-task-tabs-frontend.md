# WP-47: Concurrent per-agent task tabs (promotes ADR-0505)

- **State:** Not started
- **ADRs:** ADR-0505
- **Depends on:** none hard; soft: WP-44 Part A (schema/validator chain
  in place before the `zuno.ui` task-block addition), ADR-0212's
  conversation substrate (persistent `run_id` + transcript reload) —
  verify its implementation state before starting; the tab-per-task
  conversation model assumes it
- **Estimated files touched:** ~15

> Execute this brief as a standalone task from the repository root.
> Tracked in [docs/roadmap/okf-roadmap.md](../okf-roadmap.md).

## Goal

Each task in `zuno.tasks` opens as its own concurrent in-app tab with
its own conversation; tabs are OKF-driven, entitlement-filtered, and
`zuno.primary_task` is the default. The chat contract gains an explicit,
fail-closed `task` parameter.

## ADR references

ADR-0505 clauses 1–4. Composition with ADR-0212 (browser-tab focus vs
in-app tabs) per clause 1; enforcement stays server-side per its
Security section.

## Preconditions (verify before starting)

- Check ADR-0212's status in `docs/adr/README.md`: if its conversation
  persistence is not merged yet, execute Part A only (schema + runtime
  task parameter) and hold Part B (frontend tabs) — record the split in
  the State log.
- Read: `platform/okf/schema/zuno-okf-task-v0.2.schema.json`;
  `components/agent-runtime/app/registry.py` + `app/main.py`'s chat
  route; `components/agent-bff/main.go` chat proxy;
  `components/agent-frontend/web/src/chat/Chat.tsx`; the OpenAPI spec
  (`platform/api/`, ADR-0054 — spec first, then code).
- Component test prerequisites: agent-frontend Go tests need a real
  Redis at localhost:6379 (throwaway container); build the agent-runtime
  test venv from the component's own requirements.txt.

## Repo changes (step by step)

**Part A — contract:**
1. Schema: optional `zuno.ui.tabLabel` / `zuno.ui.icon` on task
   frontmatter; regenerate/validate all bundles.
2. OpenAPI: optional `task` on the chat request; BFF forwards it
   verbatim; Agent Runtime validates `task ∈ zuno.tasks` (404/400
   fail-closed on unknown), executes the named task's graph with that
   task's ceilings, defaults to `primary_task` when absent. Record the
   task on the ADR-0212 conversation row (or, pre-0212, in the SSE
   start event only).
3. Component tests: unknown-task rejection (security-negative),
   default-task equivalence, per-task ceiling selection.

**Part B — frontend:**
4. PatternFly `Tabs` bar in the agent chat page: one tab per declared
   task the caller's groups can reach (intersection against the policy
   files via the portal's existing OKF load path), label/icon from
   `zuno.ui`, default `primary_task`; per-tab conversation state
   (per-tab `run_id`), reopening a conversation activates its task's
   tab.
5. Frontend tests: tab render from a bundle fixture, entitlement
   filtering, per-tab conversation isolation.

## What NOT to touch

Standard list; plus: MCP Gateway enforcement path (unchanged by
design); no per-task routes (task rides the existing chat route); no
`policies/` edits.

## Acceptance checks (run from repo root; all must pass)

- Bundle validation green after the schema addition; matrix `--check`
  (WP-44) still green.
- Runtime + BFF + frontend suites green, including the
  security-negative unknown-task test.
- Absent-`task` behavior byte-identical to today (regression test).

## Operator / human follow-up (not executable by the model)

Rebuild/redeploy the three touched components; a demo user confirms
three Tekos tabs with two concurrent conversations surviving reload.

## Status updates (then re-run check_docs.py)

On merge: ADR-0505 → `Partially implemented (contract + UI merged;
live confirmation pending)`; after the operator demo → `Implemented -
see components/agent-frontend/web/src/chat/.` Index + tracker +
MEMORY.md accordingly.

## Out of scope / deferred

- ADR-0407's structured non-chat views (stays v0.4). Project-gated tab
  behavior beyond rendering (WP-55).
