# ADR-0515: Open per-conversation tabs with one browser tab per agent

- **Status:** Implemented (2026-08-21) - WP-061's repo work is merged: `zuno.prompt_examples` is a real OKF task-schema field, `conversations` gained a `sort_order` column plus reorder/hard-delete endpoints (Agent Runtime + BFF + frontend proxy), `tabTracker.ts` is now agent-keyed (one browser tab per agent), `chat/Chat.tsx` renders a closable, starred-first in-app `Tabs` bar with a "Create new chat" empty state, `ConversationList.tsx` gained a drag handle and a kebab menu (rename/star/soft-delete/hard-delete), and the masthead gained a cross-agent nav strip sourced from `portal.BuildTiles`. Bundle validation, the ADR-0503 authorization matrix `--check`, and the Agent Runtime/BFF/frontend test suites (including new reorder/hard-delete fail-closed and OpenAPI contract tests) all pass; `tsc --noEmit` is clean. The operator demo is confirmed: `agent-frontend`/`agent-bff`/`agent-runtime` rebuilt and redeployed on the real cluster, the `sort_order` migration applied cleanly (verified directly against the `agent-conversations` database, zero `NULL` rows), and live cross-agent tab-reuse, drag-reorder persistence and hard-delete irreversibility were confirmed by the operator. Residual gap, not blocking: no frontend unit-test suite exists in this component yet (no vitest/jest ever set up here), so the in-app tab/kebab/drag-reorder behavior was verified by `tsc` type-checking plus this live confirmation, not automated frontend tests.
- **Target:** OKF v0.1
- **Date:** 2026-08-21
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0505](0505-open-okf-tasks-as-concurrent-per-agent-frontend-tabs.md) (abandoned before implementation — see that record's Historical context/decision)

## Dated progress notes

### 2026-08-28 - prompt_examples was a field nobody filled, and the composer now reads it

This ADR's status line says `zuno.prompt_examples` "is a real OKF task-schema
field". True, and incomplete: the field was declared, parsed
(`internal/okf/okf.go`), carried through `chatConfig`, and read by
`Chat.tsx`'s "Create new chat" empty state - **and not one task in any of the
eight agent bundles ever declared a single example.** The whole path rendered
nothing for seven days. The pipe was laid and the tap never opened.

47 examples now exist across the 21 tasks of the six agents that have real task
sets. `cognos` and `soursage` are deliberately excluded: they are
`zuno.status: placeholder` with no chat page, so starters for a conversation
that cannot happen would be noise.

The field gained a second consumer at the same time. The chat composer was
reframed - one bordered block, message box above, actions below - and its "/"
trigger opens a two-level menu (`chat/TaskPromptMenu.tsx`): this agent's tasks,
each flying out its own examples. Choosing one fills the message box, unsent,
and returns the caret so the text can be edited.

**That menu does not select a task, and must not be read as doing so.**
agent-runtime accepts no task in the request; the chat route always executes
`primary_task` (ADR-0342). It is a writing aid. Turning it into a real task
selector would need a field through the frontend->BFF->runtime contract, graph
and `allowed_tools` selection in the runtime, and a per-task authorization
decision - its own ADR and WP, not a UI change.

Two consequences worth recording for whoever edits an agent bundle next:

- Editing any `agents/**` bundle invalidates its signature - the signed digest
  covers every file under the bundle directory, not just `agent.okf.md`.
  agent-runtime runs with `ZUNO_REQUIRE_SIGNED_BUNDLES=true`, so its next pod
  crash-loops on `failed to load OKF bundles` until the bundles are re-signed
  AND the new signatures reach the pod. Run `make d3 sign agents`.

  That verb used to stop halfway, and this note originally prescribed the
  manual repair. It no longer applies: `8320e71e` (2026-08-28) closed the gap
  the same day, after the crash-loop this ADR's own work caused.
  `ansible/playbooks/day3_sign.yml` now signs, verifies, forces the
  `agent-runtime-okf-signatures` ExternalSecret and waits for its
  `status.refreshTime` to advance (`ansible/tasks/force_externalsecret_refresh.yml`),
  deletes the pods by label - never `oc rollout restart`, which ArgoCD's
  selfHeal reverts - and gates on the rollout becoming ready. The one-hour
  `refreshInterval` on the ExternalSecret is deliberately left alone: forcing
  at the caller is correct, lowering the global interval is not.
- Agent replies now render as Markdown (`chat/Markdown.tsx`, react-markdown +
  remark-gfm). Raw HTML in a reply is inert by design and `rehype-raw` must not
  be added: the text is LLM-written with the RAG corpus in context, so an
  injected `<img onerror=...>` in an ingested document would otherwise reach
  this page.

Live-confirmed by the operator on 2026-08-28.

## Context

ADR-0505 tied in-app tab identity to *task*: one tab per `zuno.tasks`
entry. WP-47 never started, and before any code landed the design was
reconsidered — task selection is something that happens inside a
conversation, not a property that should define the tab containing it. A
user's actual mental model is simpler: one browser tab per agent they are
working in, and inside that agent, one tab per conversation they have
open.

The substrate this builds on is unchanged and already `Implemented`:
ADR-0212 gives every conversation a durable `run_id`, a transcript reload
endpoint, and a left-hand conversation list
(`components/agent-frontend/web/src/shared/ConversationList.tsx`), backed
by a `conversations` table (`run_id`, `agent_name`, `owner_sub`, `title`,
`project_id`, `archived_at`, …) plus a per-user `conversation_stars` table
in `components/agent-runtime/app/conversations.py`. Today,
`tabTracker.ts` (`components/agent-frontend/web/src/shared/tabTracker.ts`)
maps each `run_id` to a stable `window.open` target name, so opening a
conversation opens or focuses **one browser tab per conversation** — the
granularity this ADR replaces. `ConversationList.tsx` already has
star/unstar and rename (double-click) and a soft-delete (archive) action,
but no kebab menu, no drag-to-reorder and no hard-delete — its own
comment defers a kebab menu to ADR-0213. Agent-to-agent navigation today
goes through `Portal.tsx`/`internal/portal/portal.go`, a separate tile
gallery page (ADR-0008: one Go+React/PatternFly codebase per agent,
deployed once, so any change here lands for every agent uniformly).

## Decision

1. **In-app tabs are keyed by conversation, not by task.** A PatternFly
   `Tabs` bar inside the agent's chat page renders one tab per open
   conversation, each holding its own `run_id`, transcript and state. If
   a bundle declares multiple tasks, task selection happens *inside* a
   conversation (or at conversation-creation time), never as tab
   identity — this reverses ADR-0505's decision 1.

2. **One browser tab per agent; in-app tabs per conversation within it.**
   `tabTracker.ts` changes key from `run_id` to `agent`: opening an agent
   — from the portal, from a conversation link, or from the new masthead
   nav strip (decision 8) — reuses and focuses the agent's existing
   browser tab if one is open, else opens a new one. Once in that tab,
   opening a conversation from the left-hand list activates an in-app tab
   client-side; it never calls `window.open`.

3. **First visit to an agent.** If the caller has conversation history,
   the agent opens with exactly one in-app tab: the most recent
   conversation. If there is no history, the chat page shows a centered
   "Create new chat" affordance with example prompts drawn from the
   bundle. Each OKF task frontmatter gains an optional
   `zuno.prompt_examples: string[]` field (schema addition in
   `platform/okf/schema/zuno-okf-task-v0.2.schema.json`) presented to the
   user starting their first conversation — this replaces ADR-0505's
   abandoned `zuno.ui.tabLabel`/`zuno.ui.icon` proposal, which had no
   purpose once tabs stopped being task-keyed.

4. **In-app tabs are closable.** Each tab carries an "x"; closing it
   removes the conversation from the open set for the session only — it
   neither archives nor deletes the conversation.

5. **Starred conversations sort left.** Among open in-app tabs, tabs for
   starred conversations are ordered before non-starred ones.

6. **The conversation list gets a right-aligned kebab menu per row**,
   consolidating rename, star/unstar, and delete — both soft (today's
   archive behavior, unchanged) and hard. Hard delete is a new,
   irreversible operation with no backend equivalent today (only
   `archive_conversation` exists); it permanently purges the conversation
   row and its checkpoint/message history and must be confirmed in the
   UI before it fires. This replaces the current separate star-icon /
   trash-icon / double-click-to-rename affordances.

7. **A drag handle left of each conversation's title reorders the list
   manually.** Drop persists the new order server-side (a `conversations`
   table gains an explicit ordering column — none exists today) so order
   survives reload and is per-user like starring.

8. **The masthead gains a cross-agent navigation strip**: every agent the
   caller is entitled to, shown as name-and-color links only (no other
   metadata), each routed through decision 2's per-agent browser-tab
   reuse-or-open logic. The list is sourced from the same
   entitlement-filtered agent set `Portal.tsx`/`portal.go` already reads
   from `agents/*/agent.okf.md`, exposed to `agent-frontend` so a full
   Portal page visit is not required to switch agents.

## Consequences

The tab-per-task coupling ADR-0505 introduced is fully removed before it
ever shipped; task selection (if a bundle declares more than one task)
becomes a conversation-level concern, decoupled from tab rendering.
`tabTracker.ts` narrows to agent-level reuse, and a new client-side in-app
tab layer is added on top of it — two composed but distinct mechanisms
instead of one. `ConversationList.tsx` gains ordering and hard-delete,
both new server-side capabilities. WP-061 implements this ADR; WP-47 is
marked Abandoned rather than reused, since no code was written against
it.

## Security considerations

The masthead agent-nav strip and per-agent tab reuse are UX conveniences;
per-agent access remains enforced server-side exactly as ADR-0040
already requires (entitlement is never inferred from what the frontend
chooses to render). Hard-delete must be scoped to the conversation's
`owner_sub` and requires the same authenticated session as any other
conversation mutation — it introduces a new irreversible action, so it
must never be reachable without explicit per-row confirmation, and audit
logging should record hard-deletes distinctly from soft-deletes given the
data loss is permanent. Reorder and rename remain per-user, additive
operations with no authorization implications beyond today's.

## Operational considerations

The conversation ordering column and the hard-delete path both need a
schema migration in the conversations database (ADR-0212's store,
`components/agent-runtime/app/conversations.py`). The `prompt_examples`
schema addition rides the existing bundle-baking path used by every other
OKF field — no new config channel. No OpenAPI contract change is required
beyond the new reorder and hard-delete endpoints, following ADR-0054's
spec-first flow.

## Acceptance criteria

- Opening an agent that already has a browser tab open focuses that tab
  instead of opening a duplicate; opening an agent for the first time (or
  after its tab was closed) opens exactly one new browser tab.
- Inside an agent's tab, opening two different conversations produces two
  independent, closable in-app tabs; starred conversations' tabs sort
  left of non-starred ones.
- A user with no conversation history sees a centered "Create new chat"
  state with example prompts sourced from `zuno.prompt_examples`; a user
  with history sees one in-app tab open on their most recent conversation.
- The conversation list's kebab menu performs rename, star/unstar, soft
  delete and hard delete; hard delete requires confirmation and is
  irreversible; drag-reordering persists across reload.
- The masthead nav strip shows only agents the caller is entitled to, and
  clicking one reuses that agent's already-open browser tab when present.

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0008](0008-use-one-frontend-and-one-bff-deployment-per-agent.md)
- [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md)
- [ADR-0044](0044-use-patternfly-react-for-the-agent-frontend.md)
- [ADR-0054](0054-define-the-bff-contract-openapi-first.md)
- [ADR-0212](0212-introduce-persistent-navigable-chat-conversations.md)
- [ADR-0213](0213-introduce-role-based-conversation-sharing.md)
- [ADR-0407](../roadmap/adr-decisions-v0.4.md#adr-0407-add-specialized-task-oriented-frontend-views)
- [ADR-0503](0503-make-each-okf-bundle-state-its-complete-authorization-contract.md)
- [ADR-0505](0505-open-okf-tasks-as-concurrent-per-agent-frontend-tabs.md) (superseded by this ADR)
- [ADR-0512](0512-introduce-project-bound-tasks-with-salesforce-verified-context.md)
