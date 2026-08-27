# WP-089: Projects sidebar, project dialog and read-only tabs (promotes ADR-0527)

- **State:** Repo work merged (2026-08-27)
- **ADRs:** ADR-0527 clause 9 (Partially implemented -> Implemented once this WP lands and the live two-persona pass runs)
- **Depends on:** WP-088 (the `/api/projects` and `/api/groups` routes, and `Conversation`'s new `project_id`/`role` fields)
- **Estimated files touched:** ~10

> Execute this brief as a standalone task from the repository root.
>
> Tracked in [docs/roadmap/v0.1-v0.3-implementation-roadmap.md](../v0.1-v0.3-implementation-roadmap.md) Phase 21.

## Goal

Replace ADR-0212's flat conversation list with a two-block sidebar (Projects,
then Conversations), add the two-tab project dialog that commits every change in
one save, and give conversation tabs a real read-only mode - removing
`ShareDialog.tsx` and the conversation-level sharing UI.

## ADR references

Primary: [docs/adr/0527-introduce-the-project-as-the-sharing-and-context-boundary.md](../../adr/0527-introduce-the-project-as-the-sharing-and-context-boundary.md)
clause 9, plus clauses 2-4 for exactly which control each role may see.

Read also: [ADR-0515](../../adr/0515-per-conversation-tabs-one-browser-tab-per-agent.md)
(the in-app tab model and the row layout this WP must preserve verbatim),
[ADR-0044](../../adr/0044-use-patternfly-react-for-the-agent-frontend.md)
(PatternFly is the component vocabulary; there is no CSS file in `src` - inline
styles with `--pf-t--global--*` tokens only).

## Preconditions (verify before starting)

- WP-088 merged; `cd components/agent-bff && go test ./...` green.
- Read `web/src/shared/ConversationList.tsx` in full (the row `.map()` body at
  the heart of this WP), `web/src/shared/ShareDialog.tsx` (the debounced
  colleague search and greyed-out-ineligible rendering both carry over),
  `web/src/chat/Chat.tsx` (`TabState`, `openConversation`, the composer and the
  `busy` alert this WP's read-only alert mirrors), `web/src/shared/types.ts`.
- Node locally is 16, which breaks `vite build` and eslint in some setups;
  `npx tsc --noEmit` is the gate that must pass regardless.

## Repo changes (step by step)

1. **Extract `ConversationRow.tsx` first, as a pure no-op refactor.** Move
   `ConversationList.tsx`'s existing row body - drag handle, star, inline rename
   input, title button, kebab - into `web/src/shared/ConversationRow.tsx` with
   no behavioural change, and confirm `npx tsc --noEmit` is green before going
   further. This is what makes ADR-0527's "conversation rows keep ADR-0515's
   exact layout in both blocks" verifiable rather than aspirational.
2. **`web/src/shared/projects.ts` (new).** Types (`ProjectRole`, `Project`,
   `ProjectDetail`, `ProjectGrant`, `DeletePreview`, `RealmGroup`,
   `PROJECT_CONTEXT_MAX_CHARS = 54000`) and fetch wrappers, reusing
   `conversations.ts`'s `parseOrThrow` shape. Move `Colleague`/`getColleagues`
   here - they are a project-RBAC concern now.
3. **`web/src/shared/ProjectDialog.tsx` (new).** PatternFly `Modal` + `Tabs`.
   All edits mutate a local `draft`; a single `Save` issues one `POST`/`PUT`.
   Description tab: title, context `TextArea` with a live `n / 54000` helper
   that turns `error` past the limit, and the optional Salesforce field.
   RBAC tab (rendered only for `admin`): Users subsection fed by the 300 ms
   debounced colleague search lifted from `ShareDialog.tsx` - ineligible
   candidates stay visible but greyed out and disabled, an ADR-0213 product
   requirement ADR-0527 restates - and Groups subsection fed by
   `getRealmGroups`, whose select is disabled with an explicit "group directory
   unavailable" message on 503 rather than rendering an empty-looking picker.
   Save is disabled when the title is empty, the context is over the limit, or
   the grant set would contain no subject-scoped `admin`. A danger `Delete
   project` action calls the delete-preview then confirms with the counts.
4. **`web/src/shared/ProjectRow.tsx` (new).** Fold caret, title button (opens
   the dialog), `+` (new conversation in this project), kebab with Modify and
   Delete.
5. **`ConversationList.tsx` restructure.** Two blocks with small-caps headings,
   each preceded by a fold-all folder button and followed by a `+`; a `Divider`
   between them. Fold state per project and per block persisted in
   `localStorage`, the same way the sidebar width already is. `refresh()`
   fetches projects and conversations in parallel; the list splits on
   `project_id === null`. The search box stays above both blocks and filters
   both. Drag-reorder is enabled only for the caller's own conversations and
   only when unfiltered (see the out-of-scope note).
   Props change: `onOpenConversation` now takes the whole `Conversation` (the
   tab needs `project_id` and `role`); add `projectsURL`, `groupsURL`,
   `onNewConversationInProject`.
6. **`chat/Chat.tsx`.** `TabState` gains `projectId` and `role`;
   `openConversation(c: Conversation)` and
   `openNewConversation(prefill, projectId)` seed them; `send()` includes
   `project_id` only on a conversation with no `run_id` yet, and the SSE `start`
   handler captures the server's value. When `role` is `read` or `clone`, render
   an inline `Alert` in place of the composer - the same pattern as the existing
   409 `busy` alert, which stays.
7. **Removals.** Delete `web/src/shared/ShareDialog.tsx`; delete
   `MembershipRole`, `Member`, `listMembers`, `grantMembership`,
   `revokeMembership`, `transferOwnership` from `conversations.ts`; delete the
   `Share` kebab item and the `New conversation` primary button (replaced by the
   two block headers).
8. **`web/src/shared/types.ts`.** Add `projectsURL` and `groupsURL` to
   `ChatConfig`, mirroring `internal/chat/chat.go`'s `chatConfig` - nothing
   enforces that mirror, so keep them in step by hand.

## What NOT to touch

- `ConversationRow.tsx`'s layout after step 1 - the row must stay
  byte-equivalent to today's in both blocks.
- The SSE parsing in `shared/sse.ts` and `chat/types.ts`.
- `tabTracker.ts` - agent-scoped, used only by the masthead nav strip.
- Any Go file (WP-088 already registered the routes and config fields).
- The 409 `busy` state, which the write lease still produces.

## Acceptance checks (run from repo root; all must pass)

- `cd components/agent-frontend/web && npx tsc --noEmit`
- `cd components/agent-frontend/web && npm run lint`
- `cd components/agent-frontend/web && npm run build`
- `cd components/agent-frontend && go build ./... && go test ./...`
- `python3 platform/docs/check_docs.py`

## Operator / human follow-up (not executable by the model)

- Rebuild and redeploy the agent frontend, then run the live two-persona pass
  ADR-0527's acceptance criteria describe (create, share to a user, share to a
  group, verify all four roles in the UI **and** as 403s at the API, clone,
  cascade delete). This requires the `zuno-admin-api` provisioning WP-088's
  follow-up lists - without it the RBAC tab cannot add anyone.
- This component has no frontend unit-test suite (the same gap ADR-0213's and
  ADR-0515's status lines both record), so the live pass is the only functional
  verification these components get.

## Status updates (then re-run check_docs.py)

- After merge: ADR-0527 -> `Partially implemented (repo work complete; live
  two-persona pass pending)`; Phase 21 tracker row -> `Repo work merged`.
- After the live pass: ADR-0527 -> `Implemented`; tracker -> `Done`; a dated
  `MEMORY.md` bullet.

## Out of scope / deferred

- Per-subject conversation ordering. `conversations.sort_order` is one shared
  column, so reordering a colleague's conversation would move it in their list
  too; this WP simply disables the drag handle for conversations the caller does
  not own. A `conversation_sort_order` table is a separate decision.
- A "shared with me" filter or separate view - the Projects block already
  answers it.
- Project drag-reorder: projects sort by star then title.
