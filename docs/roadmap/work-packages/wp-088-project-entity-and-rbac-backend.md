# WP-088: The project entity, its RBAC and its context (promotes ADR-0527)

- **State:** Not started
- **ADRs:** ADR-0527 (Proposed -> Partially implemented after this WP; Implemented after WP-089's UI lands and a live two-persona pass runs)
- **Depends on:** ADR-0212's conversation substrate and ADR-0515/WP-061's list structure (both Implemented). Supersedes WP-066, whose merged code this WP removes.
- **Blocks:** WP-089 (needs these endpoints and the widened `Conversation` shape), WP-090 (needs `projects.salesforce_*` and the server-resolved `project_id` on graph state)
- **Estimated files touched:** ~20

> Execute this brief as a standalone task from the repository root. This WP
> touches the BFF OpenAPI contract - sequence the contract step as one atomic
> change (spec + Go code + contract tests together), per ADR-0054.
>
> Tracked in [docs/roadmap/v0.1-v0.3-implementation-roadmap.md](../v0.1-v0.3-implementation-roadmap.md) Phase 21.

## Goal

Make the project a real object: a `projects` table that owns every `project_id`,
a four-role grant table addressing subjects and business-role groups, the
conversation surface re-scoped from `owner_sub` to project membership, the
project context injected as budgeted background into every turn, and
`project_memberships` demoted to a projection - while removing ADR-0213's
conversation-level sharing entirely.

## ADR references

Primary: [docs/adr/0527-introduce-the-project-as-the-sharing-and-context-boundary.md](../../adr/0527-introduce-the-project-as-the-sharing-and-context-boundary.md)
(read fully - clauses 1-8 are all in this WP; clause 9 is WP-089).

Read also: [ADR-0209](../../adr/0209-introduce-project-scoped-agent-memory.md)
(the `project_memberships` contract this WP projects into),
[ADR-0212](../../adr/0212-introduce-persistent-navigable-chat-conversations.md)
(the substrate), [ADR-0213](../../adr/0213-introduce-role-based-conversation-sharing.md)
(what is being removed, and the write lease that stays),
[ADR-0215](../../adr/0215-carry-conversation-history-into-agent-prompts-with-budgeted-compaction.md)
(the injection point and budget pattern the project context copies).

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0; ADR-0527/0528 are in the index.
- Read, in this order: `components/agent-runtime/app/conversations.py` in full
  (the `_DDL`, `record_turn`'s documented must-not-fail-closed exception,
  `list_conversations`, the write lock); `app/main.py`'s `_resolve_run_id`,
  `_initial_state`, `_bind_project_if_required`, `agent_chat` and `_stream_chat`;
  `app/graph/state.py` (the comment on `run_id` explaining that undeclared keys
  are silently dropped); `app/graph/nodes.py`'s `reason_node` and
  `app/graph/arkos_nodes.py`'s `draft_node` (**two** injection points);
  `app/registry.py`'s `zuno.memory.history` parsing;
  `components/rag-service/app/search.py`'s `_check_project_membership`;
  `components/agent-bff/{main.go,openapi.json,contract_test.go}` and
  `internal/{runtime,keycloak}/client.go`.
- A component venv exists: `components/agent-runtime/.venv` built from that
  component's own `requirements.txt` (system python will not do).

## Repo changes (step by step)

1. **Schema.** Append to `conversations.py`'s `_DDL`, in this order: `projects`,
   `project_grants` (with the partial unique indexes on `(project_id, subject)`
   and `(project_id, group_name)`), `project_stars`; then the migration -
   `UPDATE conversations SET project_id = NULL, project_id_verified_at = NULL`
   for any value with no `projects` row, with a `RAISE NOTICE` of the count,
   **then** the `fk_conversations_project` foreign key in a guarded `DO $$`
   block, then `ix_conversations_project`; then `DROP TABLE IF EXISTS
   conversation_memberships` (also `RAISE NOTICE`-ing its row count first).
   Ordering is load-bearing: the DDL is fail-fast inside `pool_context()`, so
   adding the constraint before the cleanup crash-loops the pod.
2. **`app/projects.py` (new).** `Role`, `_ROLE_RANK` (`read < clone < write <
   admin`), `effective_role`, `list_projects`, `get_project`, `create_project`,
   `save_project` (full-state replace, single transaction, projection push
   before commit), `_assert_last_admin_survives`, `delete_preview`,
   `archive_project_cascade`, `reconcile_projections`, `_business_role_groups`
   (strips the leading `/`, drops the `agent_` prefix - applied on both the
   grant and the resolution side). Every function fails closed on a `None` pool
   via `_require_pool`, matching `conversations.py`.
3. **`app/clients/project_membership_client.py` (new).** `PUT
   {RAG_SERVICE_URL}/v1/projects/{project_id}/memberships` with
   `{revision, members[]}`; same httpx/timeout shape as
   `project_memory_client.py`. rag-service side: `replace_project_memberships`
   in `app/project_memory.py` (delete-then-insert in one transaction, applied
   only when `revision >= max(stored)`, otherwise `applied: false` with 200) and
   the route in `app/main.py`; `data/rag/schema/006_project_membership_projection.sql`
   adds the `revision` column and the two partial unique indexes.
   `app/search.py`'s `_check_project_membership` gains a docstring line and **no
   code change**.
4. **`conversations.resolve_access`.** One statement joining `conversations`,
   `projects` and a `LEFT JOIN LATERAL` over `project_grants` ordered by role
   rank - one round trip, not three. It replaces every `get_role` call site.
   Delete `get_role`, `list_members`, `grant_membership`, `revoke_membership`,
   `transfer_ownership`, `get_project_binding`.
5. **`list_conversations` rewrite.** From `owner_sub`-only to: project-less
   conversations the caller owns, plus every non-archived conversation of any
   live project the caller holds a grant on, still scoped to `agent_name`;
   returns `project_id` and the caller's `role` per row. **Write the
   security-negative test before wiring anything to it** (ADR-0527's Security
   considerations lists the five fixtures it must cover).
6. **Metadata rights.** Re-scope `rename_conversation`, `archive_conversation`,
   `set_star`, `reorder_conversations`, `hard_delete_conversation` per ADR-0527
   clause 4's table. `hard_delete_conversation` stays owner-only.
   `clone_conversation` keeps the source's `project_id`, sets the cloner as
   `owner_sub`, and derives the title (`_derive_clone_title`).
7. **Endpoints.** `GET|POST /v1/projects`, `GET|PUT|DELETE
   /v1/projects/{project_id}`, `GET /v1/projects/{project_id}/delete-preview`,
   `PUT|DELETE /v1/projects/{project_id}/star` - global, outside
   `/v1/agents/{agent}`. Remove the three members routes and the owner-transfer
   route. `schemas.py`: `PROJECT_CONTEXT_MAX_CHARS = 54000`, `ProjectGrantSpec`
   (XOR validator mirroring the SQL constraint), `CreateProjectRequest`,
   `SaveProjectRequest`; delete `GrantMembershipRequest` and
   `TransferOwnershipRequest`.
8. **`agent_chat` wiring.** Resolve access, then the write check (`write`/`admin`
   only), then `record_turn` with the **server-resolved** `project_id`, then the
   lease. Remove `"project_id": payload.project_id` from `_initial_state` - that
   single deletion is the whole "server-verified project" guarantee. On resume,
   ignore `payload.project_id` and log a mismatch. Add `project_id` to the SSE
   `start` event and to `ChatResponse`.
9. **Write-lease renewal.** Renew inside `_stream_chat`'s event loop, throttled
   to ~10s with a `time.monotonic()` guard (never a DB call per token); on
   renewal failure emit an `error` SSE and stop rather than continue
   unprotected. This is the gap ADR-0213 specified and its implementation
   omitted.
10. **Project context injection.** `state.py`: declare `project_context` and
    `project_classification` on `AgentState` (undeclared keys are silently
    dropped). `history.py`: `truncate_to_token_budget` (char/4, cut on
    whitespace). `registry.py`: `PROJECT_CONTEXT_TOKEN_BUDGET_DEFAULT` and
    `zuno.memory.project_context.{enabled,token_budget}` parsing, plus the
    `platform/okf/schema/` entry beside `history`. Inject in **both**
    `nodes.py:reason_node` and `arkos_nodes.py:draft_node`, after the summary
    block, under the delimiter ADR-0527 clause 5 names. Fold the project
    classification into `retrieve_node`'s `_escalate` so ADR-0034 covers it.
11. **Contract (atomic commit).** `openapi.json` + `internal/runtime/client.go`
    + `main.go` handlers + `contract_test.go` together: add the project paths
    and schemas and `GET /api/groups`; widen `Conversation` (`project_id`,
    `role`), `ChatResponse` and the SSE start event; remove the three
    members/owner paths and their six schemas and six contract tests.
    `internal/keycloak/client.go` gains `RealmGroups` (needs `query-groups` on
    the service account - never `manage-users`). `listGroupsHandler` returns
    **503** both when `adminClient == nil` and on any Keycloak error including
    403, never a 200 with an empty list.
12. **agent-frontend Go.** `main.go`: register the seven new proxy paths, remove
    the four members/owner ones - `ConversationsProxyHandler` is
    path-transparent, so no handler change. `internal/chat/chat.go`: add
    `ProjectsURL` and `GroupsURL` to `chatConfig`.
13. **Tests.** `tests/test_projects.py` and
    `tests/test_project_context_injection.py` (new), `tests/test_conversations.py`
    (edited) - see ADR-0527's last acceptance bullet for the required coverage.
    Follow this component's convention: a standalone script with a `TESTS` list
    and an `asyncio.run` driver, not pytest.

## What NOT to touch

- The Decision text of any existing ADR (only ADR-0213's and ADR-0512's
  `**Status:**` lines were amended, already done alongside ADR-0527/0528).
- `components/rag-service/app/search.py`'s `_check_project_membership` logic -
  docstring only. The projection must fit the table as it is.
- MCP Gateway authorization (`components/mcp-gateway/app/policy.py`) - unchanged
  by this decision.
- The quota header gate in `model_router.py` and the eight `nodes.py` call
  sites - that is WP-090's, deliberately, so this WP stays reviewable.
- `policies/tools/tool-policy.yaml` grants; the Keycloak realm JSON.
- `gitops/apps/*` `targetRevision`; chart image tags.

## Acceptance checks (run from repo root; all must pass)

- `cd components/agent-runtime && .venv/bin/python3 tests/test_projects.py`
- `cd components/agent-runtime && .venv/bin/python3 tests/test_project_context_injection.py`
- `cd components/agent-runtime && for t in tests/test_*.py; do .venv/bin/python3 "$t" || exit 1; done`
- `python3 platform/api/lint_openapi.py` (exit 0)
- `cd components/agent-bff && go build ./... && go test ./...`
- `cd components/agent-frontend && go build ./... && go test ./...` (needs a throwaway Redis on localhost:6379)
- `python3 platform/docs/check_docs.py && python3 platform/docs/check_knowledge_refs.py`

## Operator / human follow-up (not executable by the model)

- Provision the `zuno-admin-api` Keycloak confidential client and its Vault
  secret - still outstanding from WP-066 - and add the `realm-management`
  `query-groups` role alongside WP-066's `view-users`/`query-users`. Until then
  both `GET /api/colleagues` and `GET /api/groups` answer 503, by design.
- Rebuild and redeploy `agent-runtime`, `rag-service`, the agent BFF and the
  agent frontend; confirm the startup DDL applied (the two `NOTICE` lines) on a
  database that still holds pre-existing `conversations.project_id` values.

## Status updates (then re-run check_docs.py)

- After merge: ADR-0527 -> `Partially implemented (backend, contract and
  projection merged; frontend pending WP-089, live pass pending)`; index row to
  match; Phase 21 tracker row -> `Repo work merged`.

## Out of scope / deferred

- All frontend React work (WP-089) and the quota/telemetry re-keying (WP-090).
- Per-subject conversation ordering: `conversations.sort_order` is a single
  shared column, so a shared conversation reorders for every viewer. WP-089
  disables the drag handle for non-owners; a `conversation_sort_order` table is
  a separate decision.
- Live push/kick on revocation - revocation stays soft, as under ADR-0213.
- Dropping `conversations.project_id_verified_at`, which WP-090 stops writing;
  keep the column one release and drop it separately.
