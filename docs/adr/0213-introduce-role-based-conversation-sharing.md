# ADR-0213: Introduce role-based conversation sharing between colleagues

- **Status:** Superseded by [ADR-0527](0527-introduce-the-project-as-the-sharing-and-context-boundary.md) (2026-08-27) - sharing moves from the conversation to the project: `conversation_memberships`, the reader/actor/cloner vocabulary, the five per-conversation membership endpoints and `ShareDialog.tsx` are removed rather than migrated, which is safe precisely because this ADR was never provisioned live (`GET /api/colleagues` has always answered 503 for want of the `zuno-admin-api` Keycloak client, so no sharing row ever existed in service). Two clauses survive into ADR-0527: the single-active-writer lease (`conversation_write_locks`, whose never-implemented mid-stream renewal ADR-0527 requires) and the Keycloak Admin API trust boundary (`internal/keycloak`, `GET /api/colleagues`), which ADR-0527 reuses for the project RBAC tab and extends with `GET /api/groups`. Historical record of what WP-066 merged on 2026-08-21: both ACL tables; `_resolve_run_id`/`transcript_endpoint` widened to any granted role; `agent_chat`'s owner/actor write check and the lease acquired after `record_turn` and released on every exit path including client disconnect; five Agent Runtime endpoints mirrored through agent-bff proxies and the OpenAPI contract; the `internal/keycloak` package; and the frontend share dialog, 409 busy state and kebab additions.
- **Target:** v0.6 (retargeted from v0.7 on 2026-08-30 — v0.7 split into a short-term closeout band (v0.6) and a long-term/harder band (v0.7); this item and its already-closed siblings ADR-0105/ADR-0206/ADR-0218 move to v0.6, while ADR-0111/ADR-0115 (externally blocked) and ADR-0352 (large not-started effort) remain in v0.7. Previously retargeted from v0.2 on 2026-08-26 — roadmap reprioritization, grouped into v0.7's second deferred-items set alongside ADR-0105/ADR-0206, unrelated to WP-04's GitHub-Actions release-automation theme)
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0212 makes conversations persistent, listable, single-owner objects, but strictly single-user: no mechanism exists for a colleague to read, continue, or clone someone else's conversation. `_resolve_run_id`'s ownership check (`components/agent-runtime/app/main.py:206-236`) is exactly the single-subject assumption this ADR must widen, while still failing closed for anyone with no granted role at all.

ADR-0040's two-dimensional RBAC - Keycloak `agent_<name>` entitlement groups gate which agents a user can open at all, separate business-role groups (sales, consultant, adv, finance, board, etc.) gate data/tool access inside an agent - governs today's access model, but there is no existing API to look up a *third party's* group membership on demand: group claims only ever arrive via the caller's own JWT/session (ADR-0042). Sharing a conversation with a named colleague requires a new, live lookup capability that does not exist anywhere in this codebase today.

ADR-0209's `project_memberships` table (`data/rag/schema/005_project_memory.sql`) is the direct structural precedent for a data-driven (not Keycloak-group-driven) ACL, deliberately kept as data rather than a per-project Keycloak group because the realm is static GitOps while projects are created ad hoc at runtime - the same reasoning applies here. That table is binary (member or not); this ADR needs a `role` column it doesn't have, so the ACL table here is adapted from that precedent, not reused verbatim.

## Decision

**Roles.** Exactly one **Owner** per conversation at a time: a plain `conversations.owner_sub` column (ADR-0212), not a membership row, so there is never a possibility of two disagreeing "owner" rows. The owner is implicitly admin (full rights, can grant/revoke any role) and can transfer ownership; the outgoing owner is automatically downgraded to an `actor` membership rather than losing access outright. Three additive, non-owner roles live in a new table:

```sql
CREATE TABLE IF NOT EXISTS conversation_memberships (
    id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id      text        NOT NULL REFERENCES conversations(run_id),
    subject     text        NOT NULL,
    role        text        NOT NULL CHECK (role IN ('reader', 'actor', 'cloner')),
    granted_by  text        NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_conversation_memberships_run_subject UNIQUE (run_id, subject)
);
CREATE INDEX IF NOT EXISTS ix_conversation_memberships_run_id ON conversation_memberships (run_id);
CREATE INDEX IF NOT EXISTS ix_conversation_memberships_subject ON conversation_memberships (subject);
```

- **Reader**: read-only - can view the conversation but cannot send messages.
- **Actor**: read + write - can continue the conversation, subject to the single-active-writer lock below.
- **Cloner**: read + clone - can copy the conversation into a brand-new, independently-owned conversation, but cannot write to the original.

**Access check.** Extends `_resolve_run_id`: `identity.sub == conversations.owner_sub` grants owner rights; otherwise a matching `conversation_memberships` row grants that role's rights; otherwise deny (403) - the same fail-closed shape ADR-0103's existing negative test already exercises for an unrelated subject, now generalized from "the one original subject" to "the owner or any granted role." Read paths (`/transcript`, `GET` conversation) accept any of the four roles; the write path (`POST .../chat`) requires owner or actor.

**Single active writer.** Two collaborators must never race on the same LangGraph checkpoint thread. A short-TTL lease table enforces one writer at a time:

```sql
CREATE TABLE IF NOT EXISTS conversation_write_locks (
    run_id           text        PRIMARY KEY REFERENCES conversations(run_id),
    holder_sub       text        NOT NULL,
    acquired_at      timestamptz NOT NULL DEFAULT now(),
    lease_expires_at timestamptz NOT NULL
);
```

The lease (30 seconds) is acquired inside the existing `POST /v1/agents/{agent}/chat` endpoint immediately after the write-role check, renewed while `_stream_chat` yields token events, and released in a `finally`/on-disconnect handler, with the TTL as the fallback for a hard crash. A losing acquisition returns HTTP 409; the frontend shows a "busy" state rather than queuing or interleaving the request.

**Colleague lookup.** A new `GET /api/colleagues?q=<text>` endpoint on `agent-bff` (not `agent-frontend`, not `agent-runtime`) calls Keycloak's Admin REST API (search users, then per-candidate group membership) using a client-credentials grant against a new confidential client, `zuno-admin-api`, Vault-seeded per ADR-0024 and scoped to the minimal `realm-management` `view-users`/`query-users` service-account roles only - never `manage-users`. This is a genuinely new outbound trust boundary for `agent-bff`, which today only performs read-only JWKS-based token verification (`internal/jwks`); it must be reviewed alongside ADR-0037's existing network/workload-identity boundaries. A candidate is eligible - shown selectable rather than greyed out - only if they hold both the agent's `agent_<name>` entitlement group and at least one business-role group in common with the sharer's own business-role groups; the BFF computes this and returns `{sub, displayName, eligible}[]` so the frontend can render ineligible colleagues greyed out rather than hiding them, per the product requirement.

`agent-runtime`'s grant endpoint (below) does not itself re-verify the target subject's Keycloak groups; it trusts the eligibility already computed by `agent-bff`, its sole caller for this route over the same in-cluster-only network path ADR-0008/ADR-0037 already establish for the chat proxy. This is an accepted, explicitly-documented trust assumption - not defense-in-depth against a compromised or buggy BFF - flagged here for reviewer sign-off rather than left implicit.

**Endpoints** on `agent-runtime` (which already owns `conversations`, so it owns this ACL table too):
- `GET /v1/agents/{agent}/runs/{run_id}/members` - list the ACL (owner-only).
- `PUT /v1/agents/{agent}/runs/{run_id}/members/{subject}` - body `{role}`; owner-only.
- `DELETE /v1/agents/{agent}/runs/{run_id}/members/{subject}` - revoke; owner-only; soft (see below).
- `PATCH /v1/agents/{agent}/runs/{run_id}/owner` - body `{new_owner_sub}`; owner-only; ownership transfer.
- `POST /v1/agents/{agent}/runs/{run_id}/clone` - owner or cloner only; copies the checkpoint's `channel_values` into a fresh `thread_id`, inserts a new `conversations` row (`owner_sub` = caller, `source_run_id` = the original) with no live sync back.

`agent-bff` adds `GET /api/colleagues` (new, BFF-only, no forward to `agent-runtime`) plus thin proxies for members/owner/clone, mirroring ADR-0212's proxy pattern.

**Revocation.** Soft: an already-open browser tab keeps working until its next reload or send action, at which point the same fail-closed access check above denies it. No live push/kick mechanism is introduced.

**Frontend** (`components/agent-frontend/web/src`): `shared/ShareDialog.tsx` (colleague search, role picker, member list with revoke, ineligible candidates rendered greyed out); a "busy"/disabled-composer state in `chat/Chat.tsx` on HTTP 409; a role badge and a Clone action added to ADR-0212's `ConversationList.tsx`.

## Consequences

Conversations become genuinely collaborative without any change to Keycloak's static realm configuration - sharing is data (`conversation_memberships`), not identity infrastructure, mirroring ADR-0209's own reasoning for `project_memberships`. `agent-bff` gains a real outbound dependency on Keycloak's admin plane for the first time. `agent-runtime` gains write-serialization logic it never needed under ADR-0103's original single-user assumption.

## Security considerations

The Keycloak Admin API dependency from `agent-bff` is a new network path and a new credential class that must be reviewed against ADR-0037's network/workload-identity boundaries and given least-privilege realm-management roles only. `agent-runtime` trusting `agent-bff`'s eligibility computation (rather than re-verifying groups itself) is an intentional, explicitly-accepted trust boundary, not an oversight - it is mitigated by the route being reachable only from `agent-bff`'s in-cluster network path and by revocation being cheap; it should get explicit reviewer sign-off rather than being assumed safe by default. Soft revocation is a documented, accepted risk, not a bug: the window between revocation and the next fail-closed check is bounded by the collaborator's own next action, and the check itself is the same one ADR-0103 already proves works. The single-active-writer lock closes a genuine data-integrity gap - without it, two concurrent streaming runs against the same `thread_id` can race on checkpoint writes. Clone is effectively an authorized full-transcript export into a new, wholly independent conversation the cloner solely owns; only owner and cloner may trigger it, never reader or actor.

## Operational considerations

The write-lock lease TTL (30s) needs tuning and observability - repeated lock-contention 409s likely indicate a stuck or never-released lease rather than legitimate concurrent use, and should be alertable. Colleague search must be client-debounced; Keycloak Admin API latency and rate limits are a new operational dependency for the sharing flow specifically, isolated from the chat path itself. ACL mutations (grant, revoke, transfer, clone) are traceable by `run_id`, `subject`, and `granted_by`, mirroring ADR-0203's existing tracing requirement.

## Acceptance criteria

- Owner `consultant-a` shares a Tekos conversation with `consultant-b` as actor: `consultant-b` opens it, sees the full history via `/transcript`, and sends a message that continues the same `run_id`/checkpoint thread.
- `consultant-b` attempting to send a message while `consultant-a` has an in-flight run on the same conversation is rejected (409, "busy" UI state), never queued or interleaved; once `consultant-a`'s run completes and the lease releases, `consultant-b`'s retry succeeds.
- A colleague search returns a candidate who holds `agent_tekos` but no business-role group in common with the sharer; the UI greys them out, and a direct `PUT members/{subject}` against that candidate is independently rejected (403) at the API layer.
- Owner revokes `consultant-b`: their already-open tab keeps working until the next reload or send; the next `/transcript` load or chat POST after revocation is denied (403), the same fail-closed shape ADR-0103's existing negative test already exercises.
- `consultant-b` holding only the cloner role can clone into a new, independently-owned conversation carrying `source_run_id`, but cannot POST a message to the original.
- A security-negative test proves `agent-runtime`'s `PUT members/{subject}` endpoint is unreachable from outside `agent-bff`'s own network path (network-policy test), demonstrating the BFF-trust boundary is actually enforced, not just assumed.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0008](0008-use-one-frontend-and-one-bff-deployment-per-agent.md)
- [ADR-0012](0012-use-keycloak-as-the-central-identity-provider.md)
- [ADR-0024](0024-use-vault-for-application-secrets.md)
- [ADR-0033](0033-derive-user-identity-only-from-validated-tokens.md)
- [ADR-0037](0037-protect-mcp-servers-with-network-and-workload-identity-boundaries.md)
- [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md)
- [ADR-0042](0042-use-opaque-browser-sessions-with-server-side-token-storage.md)
- [ADR-0103](0103-persist-resumable-long-running-agent-workflows.md)
- [ADR-0209](0209-introduce-project-scoped-agent-memory.md) (contrast - unrelated; no cross-conversation memory sharing is implied by this ADR)
- [ADR-0212](0212-introduce-persistent-navigable-chat-conversations.md) (depends on - conversations must exist before they can be shared)
