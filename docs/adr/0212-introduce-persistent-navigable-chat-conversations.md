# ADR-0212: Introduce persistent, navigable chat conversations

- **Status:** Proposed
- **Target:** v0.2
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team

## Context

`components/agent-frontend` is one shared Go+React/PatternFly codebase deployed once per agent (ADR-0008: tekos, advantage, comage, finage, arkos, naveo), so a change here lands once and applies to every agent. Today it has no multi-conversation concept at all: `web/src/chat/Chat.tsx` mints a throwaway `sess-<random>-<timestamp>` id in a `React.useRef` on every page load, nothing is persisted or listed, and the frontend never captures the `run_id` that `components/agent-runtime` already returns in the SSE `start` event. ADR-0103 already persists every workflow run as a resumable LangGraph PostgreSQL checkpoint keyed by `run_id`, with a fail-closed `_resolve_run_id` check (`components/agent-runtime/app/main.py:206-236`) that refuses to resume a checkpoint unless the caller's validated token subject (`identity.sub`, per ADR-0033) matches the checkpoint's stored `user_sub`. That resume contract has existed server-side since v0.1 but has no frontend caller today - there is no way for a user to see, reopen, rename, or organize a past conversation.

There is also no left-hand navigation anywhere in `agent-frontend`: `Chat.tsx`, `web/src/portal/Portal.tsx` and `web/src/profile/Profile.tsx` all render the same bare `Masthead`-only `Page` layout, with the account menu already correctly right-aligned (`web/src/shared/UserMenu.tsx`, rendered inside PatternFly's `MastheadContent`/`Toolbar` slot).

`components/agent-runtime/app/main.py` already reconstructs a full conversation transcript from a `run_id`'s checkpoint via `_build_transcript` (~line 239), but today that function is reachable only server-side, from the ADR-0209 memory-extraction endpoint (`/v1/agents/{agent}/runs/{run_id}/extract-memory`). ADR-0209 and ADR-0103 both explicitly keep "raw conversation persistence beyond checkpoints... out of scope" for the RAG platform - `knowledge.project` (ADR-0209) stores only extracted durable facts, never raw turns, and is unaffected by this decision. This ADR deliberately narrows that "out of scope" language for one specific purpose: reloading a conversation's own history when a user reopens it is answered by extending the existing checkpoint mechanism, not by adding conversation replay to RAG.

Honest scope note: ADR-0200 (the v0.2 roadmap) framed v0.2 as maturing MCP/RAG/model-routing for the platform's existing single-agent pattern and explicitly said v0.2 "does not add a second agent" or "agent-to-agent delegation" - it did not anticipate a multi-conversation chat UI. This ADR expands that original scope; it remains targeted at v0.2 because the change is to the one shared `agent-frontend` codebase (ADR-0008), independent of how many agents are active.

## Decision

Introduce a first-class, persistent "conversation" concept, identified by the same `run_id` ADR-0103 already mints, with a left-hand conversation list in the UI and full-history reload on reopen.

**Data model** - a new dedicated database, `agent-conversations`, on the existing shared `zuno-postgresql` PGO cluster, following the same dedicated-database-on-shared-cluster precedent `gitops/charts/postgresql` already uses for the ADR-0103 checkpoint database (`checkpointDatabase` in `values.yaml`, its `externalsecret-checkpoint.yaml`, its `postgrescluster.yaml` user/database entry) and for Keycloak (ADR-0315). This is one shared database, not one per agent unlike the per-domain `rag-*` pattern (ADR-0204) - conversation metadata is operationally a single concern across every agent, not a knowledge domain. Schema is applied via an idempotent DDL step inside `agent-runtime`'s own `lifespan` startup, mirroring how `checkpointer.setup()` already bootstraps the checkpoint schema, rather than a new GitOps `job-schema-apply` chart.

```sql
-- agent-conversations database, owned by agent-runtime.
CREATE TABLE IF NOT EXISTS conversations (
    run_id        text        PRIMARY KEY,        -- LangGraph thread_id (ADR-0103)
    agent_name    text        NOT NULL,            -- OKF agent name, e.g. 'tekos'
    owner_sub     text        NOT NULL,            -- single owner (ADR-0213 makes it transferable)
    title         text        NOT NULL DEFAULT '', -- derived from the opening message
    project_id    text,                            -- optional ADR-0209 knowledge.project link
    source_run_id text        REFERENCES conversations(run_id), -- ADR-0213 clone provenance
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    archived_at   timestamptz
);
CREATE INDEX IF NOT EXISTS ix_conversations_agent_owner ON conversations (agent_name, owner_sub);

-- Personal, per-user star - a separate table (not a boolean column on
-- conversations) because a star is one user's private organizing flag,
-- not a property of the conversation itself; same reasoning ADR-0209
-- used to keep project_memberships as its own table.
CREATE TABLE IF NOT EXISTS conversation_stars (
    run_id     text        NOT NULL REFERENCES conversations(run_id),
    subject    text        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, subject)
);
```

**Endpoints** on `agent-runtime`, extending the existing `/v1/agents/{agent}/...` family:
- `POST /v1/agents/{agent}/chat` (unchanged path): when `_resolve_run_id` mints a fresh `run_id`, also insert a `conversations` row (`owner_sub = identity.sub`, `title` derived from the opening message); on resume, bump `updated_at`.
- `GET /v1/agents/{agent}/conversations` - list the caller's conversations (`owner_sub = identity.sub` under this ADR; ADR-0213 widens this to shared conversations too). Returns `{run_id, title, updated_at, starred}[]`; `?starred=true` filters.
- `GET /v1/agents/{agent}/runs/{run_id}/transcript` - a structured sibling of the existing `_build_transcript`, returning `[{role, content, ts}]` instead of one concatenated string, so the frontend can render distinct message bubbles directly. Reuses `_resolve_run_id`'s ownership check.
- `PATCH /v1/agents/{agent}/runs/{run_id}` - rename (`{title}`).
- `PUT` / `DELETE /v1/agents/{agent}/runs/{run_id}/star` - toggle the caller's personal star.

`agent-bff` gains thin proxy routes for each of the above, following the existing `chatHandler`/`apiChatRequest` shape in `components/agent-bff/main.go`: re-validate the bearer token and `agent_<name>` entitlement (ADR-0040) exactly as the chat proxy does today, then forward.

**Frontend** (`components/agent-frontend/web/src`):
- `shared/ConversationList.tsx` - a new left panel using PatternFly `Page`'s `sidebar` prop (unused today), fed by `GET /api/conversations`, starred conversations first, a search box, and a "New conversation" action.
- `shared/tabTracker.ts` - a `localStorage`-only helper (never synced across devices or browsers, per its intentionally local scope), keyed `zuno.openTabs.{agent}.{run_id}`, mapping a conversation to a named `window.open(url, tabName)` target so clicking an already-open conversation focuses that browser tab instead of duplicating it. Not every browser lets JS focus an existing tab by name without newer Tab/Window-Management permissions; the documented fallback is simply opening a new tab, never a hard failure.
- `chat/Chat.tsx` - replace the throwaway `sessionId` ref with a `runId` state: seeded from a `?run_id=` query parameter if present (fetching `/transcript` on mount to repopulate `messages`), or left unset for a brand-new conversation; captured from the SSE `start` event thereafter and sent on every subsequent request - the frontend half of ADR-0103's resume contract, exercised end-to-end for the first time. `<Page sidebar={<ConversationList .../>}>`.
- `shared/types.ts` - extend `ChatConfig` with the new endpoint bases, following the existing injected-config pattern `apiURL` already uses.

This ADR extends ADR-0103's fail-closed `_resolve_run_id` check from "must be the exact original subject" to "must be the conversation's owner" (still fail-closed; ADR-0213 widens it further to any granted ACL role). It narrows ADR-0103/ADR-0209's "raw conversation persistence beyond checkpoints remains out of scope" language: the LangGraph checkpoint, via `_build_transcript`, remains the sole source of truth for replaying a conversation - the new `conversations`/`conversation_stars` tables hold metadata only, never message content, and `knowledge.project` is untouched.

## Consequences

Every agent gains a real, persistent conversation concept and a left-nav UI; `agent-runtime` gains a second Postgres connection pool and a startup DDL step alongside the existing checkpoint pool. The frontend finally exercises ADR-0103's resume contract end-to-end, retiring the previous "one throwaway session per page load" model. `agent-bff` grows four new thin proxy routes per agent, each following the existing `chatHandler` shape.

## Security considerations

Until ADR-0213 lands, the ownership check is simply `owner_sub == identity.sub` - a direct extension, not yet a relaxation, of ADR-0103's original single-subject check. The new `agentconversations` Postgres role must be least-privilege and Vault-seeded (ADR-0024), never sharing credentials with the `agentcheckpoints` role or any `rag-*` role. `GET /v1/agents/{agent}/conversations` returns metadata (titles, timestamps) only, never message bodies, so this new, less-audited listing path cannot leak content the main chat/RAG pipeline would otherwise classify and gate. If the `agent-conversations` pool is unreachable, list/transcript/resume must fail closed (deny/503), never silently fall back to "no restriction." `tabTracker.ts`'s `localStorage` entries carry only `run_id` and a synthetic tab name - never message content, tokens, or other PII.

## Operational considerations

Startup DDL failure must fail-fast, the same posture OKF bundle validation already enforces at startup. Conversation list/transcript reads are traceable by `run_id`, `agent`, and subject, mirroring ADR-0203's existing knowledge-policy tracing requirement. No backfill is needed - this is additive; any pre-existing checkpoint threads simply have no `conversations` row and won't surface in the list until reused.

## Acceptance criteria

- A Tekos user sends a first message with no `run_id`; the SSE `start` event still carries a `run_id` unchanged from ADR-0103's contract, and a `conversations` row now exists with that `run_id`, `owner_sub` equal to the caller, and a derived title.
- Reloading the Chat page in a fresh tab (no client-side state) shows the conversation in the left panel; clicking it calls `/transcript` and repopulates the exact prior message history without any RAG or `knowledge.project` call.
- Starring a conversation persists across reloads; a different, unrelated user cannot see this conversation in their own list at all (no sharing exists yet under this ADR alone - see ADR-0213).
- Clicking an already-open conversation from the same browser focuses the existing tab (`tabTracker.ts`); the same click from a different browser or incognito profile opens a fresh tab and reloads history via `/transcript`.
- Automated tests cover: conversation-row creation on `run_id` minting, structured transcript reconstruction, and personal star toggling; a security-negative test confirms an unrelated subject still cannot resume or read another user's `run_id` (unchanged ADR-0103 behavior, now also checked at the new `/conversations`/`/transcript` endpoints).

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0008](0008-use-one-frontend-and-one-bff-deployment-per-agent.md)
- [ADR-0033](0033-derive-user-identity-only-from-validated-tokens.md)
- [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md)
- [ADR-0042](0042-use-opaque-browser-sessions-with-server-side-token-storage.md)
- [ADR-0044](0044-use-patternfly-react-for-the-agent-frontend.md)
- [ADR-0045](0045-stream-responses-end-to-end-with-sse.md)
- [ADR-0054](0054-define-the-bff-contract-openapi-first.md)
- [ADR-0103](0103-persist-resumable-long-running-agent-workflows.md)
- [ADR-0200](0200-v0.2-roadmap.md)
- [ADR-0209](0209-introduce-project-scoped-agent-memory.md)
- [ADR-0213](0213-introduce-role-based-conversation-sharing.md) (extends this ADR's ownership check to shared roles)
- [ADR-0214](0214-refresh-agent-frontend-chrome-branding-footer-and-menu-icons.md) (adds icons to this ADR's left menu)
