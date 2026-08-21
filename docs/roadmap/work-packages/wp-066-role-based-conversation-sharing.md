# WP-066: Role-based conversation sharing between colleagues (promotes ADR-0213)

- **State:** Repo work merged (2026-08-21)
- **ADRs:** ADR-0213
- **Depends on:** ADR-0212's conversation substrate (`conversations`,
  `conversation_stars`, `_resolve_run_id`) — already `Implemented`.
  ADR-0515/WP-061's kebab menu and `ConversationList.tsx` structure —
  already `Implemented`, this WP's frontend work extends it directly.
- **Estimated files touched:** ~14

> Execute this brief as a standalone task from the repository root.
> Tracked in [docs/roadmap/v0.1-v0.3-implementation-roadmap.md](../v0.1-v0.3-implementation-roadmap.md).

## Goal

Make conversations genuinely collaborative: an owner can grant a colleague
reader/actor/cloner rights on a conversation, a single-active-writer lease
prevents two collaborators racing the same LangGraph checkpoint thread, and
the frontend gains a share dialog, a busy-state on write contention, and
the kebab's two remaining actions (Share, Clone) that WP-061 explicitly
left for this WP.

## ADR references

Primary: [docs/adr/0213-introduce-role-based-conversation-sharing.md](../../adr/0213-introduce-role-based-conversation-sharing.md)

Acceptance criteria (verbatim from the ADR, six total): cross-user actor
collaboration continues the same `run_id`/checkpoint thread; a losing
write-lock acquisition is rejected (409, "busy" UI), never queued or
interleaved, and the loser's retry succeeds once the lease releases; a
colleague search result with no shared business-role group is greyed out
in the UI *and* independently rejected (403) if targeted directly; owner
revocation is fail-closed on the collaborator's next access, not a live
kick; a cloner-only collaborator can clone into a new, independently-owned
conversation but cannot write to the original; a network-policy test
proves `PUT members/{subject}` is unreachable outside `agent-bff`'s own
network path.

## Scoping decision (2026-08-21)

Build the entire feature, including the Keycloak Admin API client code
(Part C below) — but its actual provisioning (a new `zuno-admin-api`
confidential client + Vault secret) is a separate operator step the ADR
itself says needs explicit reviewer sign-off, not something to provision
silently mid-merge. Until provisioned, `/api/colleagues` fails closed
(503) — no code path is stubbed or skipped, only the external credential
is missing.

## Preconditions (verify before starting)

- Confirm ADR-0212/ADR-0515 are `Implemented` in `docs/adr/README.md`
  (they are, as of this brief's authoring).
- Read fully before editing: `components/agent-runtime/app/conversations.py`
  (the module WP-061 already extended with `sort_order`/reorder/hard-delete
  — this WP follows the same idempotent-`_DDL` and fail-closed-except-
  `record_turn` conventions); `app/main.py`'s `_resolve_run_id` (currently
  line ~227) and every owner-only endpoint that will need widening:
  `rename_conversation_endpoint` (~557), `star_conversation_endpoint`
  (~578)/`unstar_conversation_endpoint` (~594), `archive_conversation_endpoint`
  (~607), `hard_delete_conversation_endpoint` (~624, WP-061's own addition —
  the ADR predates it, so this WP must widen it too), `reorder_conversations_endpoint`
  (~505, same reason); `components/agent-bff/main.go` + `internal/runtime/client.go`
  (the existing rename/star/archive/reorder/hard-delete proxy pattern this
  WP's five new endpoints + colleague lookup follow); `components/agent-frontend/web/src/shared/ConversationList.tsx`
  (WP-061's kebab `Dropdown` — this WP adds two `DropdownItem`s, not a new
  menu); `components/agent-bff/openapi.json` (ADR-0054 spec-first: extend
  this before the Go code that implements it).
- Component test prerequisites: `agent-frontend` Go tests need a real
  Redis at localhost:6379 (throwaway container); build the
  `agent-runtime` test venv from the component's own `requirements.txt`.
- **Read the ADR's own Security considerations section before starting
  Part C** (the Keycloak Admin API trust boundary).

## Repo changes (step by step)

**Part A — data layer, access-check widening, single-writer lease:**

1. `components/agent-runtime/app/conversations.py`: add `conversation_memberships`
   and `conversation_write_locks` to the module's `_DDL` string (both
   table definitions are given verbatim in the ADR, lines 21–32 and
   43–49) — same idempotent `CREATE TABLE IF NOT EXISTS` pattern already
   used for `conversations`/`conversation_stars`. Add `get_role(pool, *,
   run_id, subject) -> Optional[Literal["owner","reader","actor","cloner"]]`
   — checks `owner_sub` first, then `conversation_memberships`, returns
   `None` if neither matches (fail-closed default). Add
   `grant_membership`, `revoke_membership`, `list_members`,
   `transfer_ownership`, `clone_conversation` (copies `conversations` row
   with a new `run_id`/`owner_sub`/`source_run_id`, does NOT touch the
   LangGraph checkpoint — that copy happens in `main.py`, mirroring how
   `hard_delete_conversation_endpoint` orchestrates two pools today). Add
   `acquire_write_lock`/`release_write_lock` against
   `conversation_write_locks` (30s TTL, `INSERT ... ON CONFLICT
   (run_id) DO UPDATE ... WHERE lease_expires_at < now()` for atomic
   steal-if-expired).
2. `app/main.py`: widen `_resolve_run_id` (~line 227) to accept any of
   owner/reader/actor/cloner via the new `get_role`, not just
   `owner_sub == identity.sub` — same fail-closed 403 shape its own
   existing negative test already exercises, generalized. Widen every
   other owner-only check listed in Preconditions the same way, choosing
   the correct minimum role per endpoint (read endpoints: any role;
   rename/star/archive/hard-delete/reorder: owner only, matching the
   ADR's silence on collaborator write access to metadata — only the
   *chat* write path becomes actor-accessible).
3. `app/main.py`'s `agent_chat`: acquire the write lease right after the
   existing write-role check, renew it while `_stream_chat` yields token
   events, release in a `finally`/disconnect handler. Losing acquisition
   → `HTTPException(409)`.
4. Tests: `tests/test_conversations.py` gains fail-closed-on-None-pool
   tests for every new function (same pattern as the existing
   `test_archive_conversation_fails_closed_on_a_none_pool` etc.), plus a
   live-logic test for `get_role`'s three-tier resolution and the write
   lock's atomic steal-if-expired behavior.

**Part B — five new Agent Runtime endpoints + BFF proxies (no Keycloak dependency):**

5. `app/main.py`: `GET/PUT/DELETE /v1/agents/{agent}/runs/{run_id}/members[/{subject}]`,
   `PATCH .../owner`, `POST .../clone` — all owner-only except clone
   (owner or cloner). Add matching Pydantic request models to
   `app/schemas.py` (`GrantMembershipRequest`, `TransferOwnershipRequest`).
6. `components/agent-bff/openapi.json`: add the five paths + request/response
   schemas, following the existing `RenameRequest`/`ReorderRequest` style
   exactly.
7. `components/agent-bff/internal/runtime/client.go` + `main.go`: five new
   client methods + HTTP handlers, identical shape to
   `ReorderConversations`/`HardDeleteConversation` (`doJSON`, `authorize`,
   `writeUpstreamError`) — no new logic needed here, this is the
   established mechanical pattern.
8. `components/agent-bff/contract_test.go`: add matching
   `TestXMatchesOpenAPISpec` entries for every new schema, same as the
   ADR-0515 block already there.
9. `components/agent-frontend/internal/chat/chat.go` + `main.go`: extend
   `ConversationsProxyHandler`'s registered routes for the five new
   paths (the handler itself is already generic — this is route
   registration only, same as WP-061's reorder/hard-delete additions).

**Part C — the Keycloak Admin API trust boundary (code-complete but
unprovisioned until the operator step below runs):**

10. `components/agent-bff`: new `internal/keycloak` package — a
    client-credentials-grant HTTP client against Keycloak's Admin REST
    API (search users by `q`, then per-candidate group membership),
    reading `KEYCLOAK_ADMIN_CLIENT_ID`/`KEYCLOAK_ADMIN_CLIENT_SECRET`
    from env (Vault-seeded, mirroring how `internal/jwks` already reads
    `KeycloakIssuerURL`/`KeycloakJWKSURL`). New `GET /api/colleagues?q=`
    handler in `main.go`: calls this client, computes eligibility
    (target holds `agent_<name>` AND shares at least one business-role
    group with the caller — the caller's own groups are already on
    their validated JWT, no extra lookup needed for that half), returns
    `{sub, displayName, eligible}[]`. This endpoint does **not** call
    `agent-runtime` — it's BFF-only, per the ADR.
11. `components/agent-bff/openapi.json` + `contract_test.go`: document
    and contract-test `/api/colleagues` the same way as every other
    endpoint.
12. Fail-closed behavior when `KEYCLOAK_ADMIN_CLIENT_ID`/`_SECRET` are
    unset (pre-provisioning): `/api/colleagues` returns 503, same
    graceful-degrade-to-hard-failure posture `conversations.py`'s
    `_require_pool` already establishes for an unconfigured dependency —
    never silently returns an empty/wrong result.

**Part D — frontend:**

13. `components/agent-frontend/web/src/shared/ShareDialog.tsx` (new):
    debounced colleague search calling `/api/colleagues`, role picker,
    member list with revoke, ineligible candidates rendered greyed out
    (per the ADR's explicit product requirement — never hidden).
14. `web/src/shared/ConversationList.tsx`: add "Share" and "Clone"
    `DropdownItem`s to the existing kebab (WP-061 already built the
    `Dropdown`/`MenuToggle` shell with Rename/Star/Delete/Delete
    permanently — this is two more items, not a new menu), plus a role
    badge per row (Owner is implicit/no badge; Reader/Actor/Cloner shown
    for conversations shared *with* the caller).
    `web/src/shared/conversations.ts`: add the five API wrapper functions
    + `getColleagues`.
15. `web/src/chat/Chat.tsx`: a disabled-composer "busy" state on HTTP 409
    from `send()`, with a retry affordance once the lease should have
    released.

## What NOT to touch

- `_build_transcript_structured`'s grouping logic (ADR-0212).
- The chat wire contract's `{session_id, message, run_id?}` shape — this
  WP adds no new chat-request fields, only a possible 409 status.
- MCP Gateway enforcement path — unchanged by design.
- ADR-0505/WP-47's abandoned brief — do not resurrect it.
- `agent-runtime`'s existing single-subject checks for endpoints *not*
  listed in Part A step 2 (e.g. the memory-extraction endpoint) — only
  the conversation-management surface widens here.

## Acceptance checks (run from repo root; all must pass)

- `components/agent-runtime`: `.venv/bin/python3 tests/test_conversations.py`
  and every other existing suite unaffected (`test_checkpointing.py`,
  `test_graph_factory.py`, etc.).
- `components/agent-bff` and `components/agent-frontend`: `go build ./...
  && go test ./...` (frontend needs a throwaway Redis container).
- `components/agent-frontend/web`: `npx tsc --noEmit`.
- `python3 platform/docs/check_docs.py` clean.
- Manual/local: with `KEYCLOAK_ADMIN_CLIENT_ID`/`_SECRET` unset,
  `/api/colleagues` returns 503, not a silent empty list — the
  fail-closed behavior Part C step 12 requires, verifiable without any
  cluster provisioning.

## Operator / human follow-up (not executable by the model)

1. **Provision the Keycloak Admin API trust boundary** — create a new
   confidential client `zuno-admin-api` in the `zuno` realm, service-account
   roles scoped to `realm-management` `view-users`/`query-users` only
   (never `manage-users`), Vault-seed its client secret per ADR-0024,
   wire it into `agent-bff`'s deployment env.
2. Rebuild/redeploy `agent-runtime`, `agent-bff`, `agent-frontend`; run
   the new DB migration (self-applies on `agent-runtime` startup, same
   as WP-061's `sort_order` column).
3. Live demo, two real personas (e.g. `consultant-01` sharing with
   `consultant-02`): all six ADR acceptance criteria, including the
   network-policy negative test for `PUT members/{subject}`.

## Status updates (then re-run check_docs.py)

- `docs/adr/0213-introduce-role-based-conversation-sharing.md`: `Status:`
  line → `Partially implemented (<date>)` once Parts A/B/D merge and
  Part C's code merges but the Keycloak/Vault provisioning (step 1 above)
  hasn't happened yet — explicitly note the trust boundary is
  code-complete but unprovisioned, not "not started." → `Implemented`
  only after the live demo (step 3) actually runs with the real
  Keycloak client wired in.
- `docs/adr/README.md`: ADR-0213 row → match.
- `docs/roadmap/v0.1-v0.3-implementation-roadmap.md`: add a new
  "Phase 10: role-based conversation sharing" section (same
  outside-the-original-40-ADR-scope convention as Phase 6/8/9), WP-066
  row → state to match.
- `MEMORY.md`: one dated bullet.

## Out of scope / deferred

- Any change to Keycloak's static realm group structure itself (business
  roles, `agent_<name>` entitlement groups) — this WP only adds a new
  service-account client, never new user-facing groups.
- Live push/kick on revocation — the ADR is explicit this is soft/lazy
  revocation only.
- A "shared with me" filter or separate view in `ConversationList.tsx` —
  the ADR's acceptance criteria only require a shared conversation to be
  openable and correctly role-gated, not a dedicated UI section for it.
