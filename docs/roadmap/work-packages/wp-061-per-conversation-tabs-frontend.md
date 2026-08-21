# WP-061: Per-conversation tabs, one browser tab per agent (promotes ADR-0515)

- **State:** Not started
- **ADRs:** ADR-0515 (supersedes WP-47/ADR-0505 — Abandoned, no code was
  written against that brief)
- **Depends on:** WP-44 Part A (schema/validator chain; already `Done`).
  ADR-0212's conversation substrate (persistent `run_id`, transcript
  reload, `conversations`/`conversation_stars` tables) is already
  `Implemented` and is a hard precondition in practice, not just soft.
- **Estimated files touched:** ~18

> Execute this brief as a standalone task from the repository root.
> Tracked in [docs/roadmap/okf-roadmap.md](../okf-roadmap.md).

## Goal

Replace per-task in-app tabs with per-conversation in-app tabs, and
replace per-conversation browser tabs with per-agent browser tabs. Add a
first-visit empty state with OKF-sourced example prompts, a conversation
kebab menu (rename/star/soft-delete/hard-delete), drag-to-reorder, and a
masthead cross-agent navigation strip.

## ADR references

ADR-0515 decisions 1–8. Enforcement of per-agent access stays server-side
per ADR-0040, unchanged by this WP.

## Preconditions (verify before starting)

- Confirm ADR-0212 is `Implemented` in `docs/adr/README.md` (it is, as of
  this brief's authoring) — the per-tab conversation model assumes its
  `conversations`/`conversation_stars` tables and transcript-reload
  endpoint exist as-is.
- Read: `components/agent-frontend/web/src/shared/tabTracker.ts`;
  `components/agent-frontend/web/src/shared/ConversationList.tsx`;
  `components/agent-frontend/web/src/chat/Chat.tsx`;
  `components/agent-frontend/web/src/portal/Portal.tsx` +
  `internal/portal/portal.go`; `components/agent-runtime/app/conversations.py`
  + its chat/conversation routes in `app/main.py`;
  `platform/okf/schema/zuno-okf-task-v0.2.schema.json`; the OpenAPI spec
  under `platform/api/` (ADR-0054 — spec first, then code).
- Component test prerequisites: `agent-frontend` Go tests need a real
  Redis at localhost:6379 (throwaway container); build the
  `agent-runtime` test venv from the component's own `requirements.txt`.

## Repo changes (step by step)

**Part A — schema, backend, contract:**

1. Schema: add optional `zuno.prompt_examples: string[]` to the task
   frontmatter schema; regenerate/validate all bundles.
2. `conversations` table migration: add an explicit ordering column
   (e.g. `sort_order`), backfilled by existing `created_at` order.
3. New reorder endpoint (BFF + Agent Runtime, OpenAPI-first) that persists
   a per-user drag-drop result; owner-scoped.
4. New hard-delete endpoint alongside the existing soft-delete
   (`archive_conversation`): owner-scoped, purges the conversation row and
   its checkpoint/message history. Keep soft-delete's current behavior
   and route unchanged.
5. `internal/portal/portal.go`: expose the entitlement-filtered
   `{name, color, href}` agent list (already computed for `Portal.tsx`)
   through a small endpoint or baked config consumable from inside an
   agent's own frontend, not just the portal page.
6. Component tests: reorder persistence, hard-delete cascade
   (row + checkpoints/messages gone, owner-scoped negative test), agent-list
   endpoint entitlement filtering.

**Part B — frontend:**

7. `tabTracker.ts`: change key from `run_id` to `agent` — reuse/focus the
   agent's browser tab if `localStorage` has one recorded, else
   `window.open` a new one and record it. Remove the `run_id`-keyed path.
8. `Chat.tsx`: add an in-app `Tabs` bar — one tab per open conversation,
   closable, starred-first ordering, opened purely client-side (no
   `window.open`). First-load behavior: open the most recent conversation
   if history exists; otherwise render a centered "Create new chat" state
   listing `zuno.prompt_examples` as clickable starter prompts.
9. `ConversationList.tsx`: add a left-aligned drag handle (persists via
   step 3's endpoint) and replace the star-icon / trash-icon /
   double-click-rename affordances with a right-aligned kebab `Dropdown`
   offering rename, star/unstar, delete (soft), delete (hard, with a
   confirmation modal given irreversibility).
10. Masthead: add the cross-agent nav strip (name + color links) sourced
    from step 5, each click going through the agent-keyed
    `tabTracker.ts` from step 7.
11. Frontend tests: in-app tab open/close/starred-sort; empty-state
    example prompts rendered from a bundle fixture; kebab menu actions;
    drag-reorder persisting through a reload; masthead strip showing only
    entitled agents and reusing an already-open tab.

## What NOT to touch

Standard list; plus: MCP Gateway enforcement path (unchanged by design);
no per-task chat routes (task selection, if any, stays inside a
conversation — this WP does not add or change chat-contract task
parameters); `policies/` untouched; do not resurrect or edit
`wp-47-task-tabs-frontend.md`'s Abandoned brief.

## Acceptance checks (run from repo root; all must pass)

- Bundle validation green after the schema addition; matrix `--check`
  (WP-44) still green.
- Runtime + BFF + frontend suites green, including hard-delete cascade
  and owner-scoping negative tests.
- Manual/automated check: opening an agent already open in another
  browser tab focuses it rather than duplicating it.

## Operator / human follow-up (not executable by the model)

Rebuild/redeploy `agent-frontend`, `agent-bff`, `agent-runtime`; run the
new DB migration; a demo user confirms cross-agent nav reuses an existing
browser tab, two conversations stay open as independent in-app tabs
inside one agent tab, drag-reorder survives a reload, and hard-delete is
confirmed and irreversible.

## Status updates (then re-run check_docs.py)

On merge: ADR-0515 → `Partially implemented (contract + UI merged; live
confirmation pending)`; after the operator demo → `Implemented - see
components/agent-frontend/web/src/chat/ and .../shared/`. Index + tracker
+ MEMORY.md accordingly.

## Out of scope / deferred

- ADR-0407's structured non-chat views (stays v0.4).
- Any change to server-side task/tool/knowledge authorization enforcement
  (ADR-0040/ADR-0503 unaffected).
- ADR-0213's role-based conversation sharing (the kebab menu leaves room
  for a future "share" action but does not add one here).
