"""ADR-0212: persistent conversation metadata (conversations,
conversation_stars) on a dedicated Postgres pool - deliberately separate
from ADR-0103's checkpoint pool (app/main.py), never sharing a connection
or credential with it (ADR-0212 Security considerations).

ADR-0527 adds the project tables (projects, project_grants, project_stars)
to this same database and drops ADR-0213's conversation_memberships. The
project lives here rather than beside ADR-0209's project_memberships in
rag-project for two reasons: every hot-path read is a join of conversations
against the project and its grants, which PostgreSQL can only do inside one
database; and this runtime deliberately holds no rag-project credential
(see app/clients/project_memory_client.py's docstring). rag-service keeps
enforcing knowledge.project access against its own project_memberships,
which app/projects.py maintains as a projection.

app/projects.py owns project CRUD and grant resolution; this module owns
the conversation surface and the one query that joins the two
(resolve_access).

Fail-closed posture, distinct from the checkpoint pool's optional
MemorySaver degrade: `pool_context()` yields None only when CONVERSATIONS_PG*
is entirely unconfigured (this feature is off for this deployment, e.g.
local dev/tests - existing chat/checkpoint behavior is unaffected). Once
configured, a connection failure at startup crashes the app (same
fail-fast posture app/main.py's checkpoint pool and OKF bundle validation
already use) - so at request time app.state.conversations_pool is never
"configured but broken", only "off" (None) or "working". Every function
below except `record_turn` raises 503 via `_require_pool` when handed
None; `record_turn` is the one exception (called unconditionally from the
hot `/chat` path) and silently no-ops instead, so ordinary chat keeps
working even when this feature isn't configured - the same graceful-degrade
posture app/main.py's `_resolve_run_id` applies to its own conversations_pool
argument.
"""
from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Literal, Optional

# ADR-0527: the four project roles, in ascending order of power. They form
# a TOTAL order - cloning exposes nothing a reader cannot already see (the
# cloner holds the whole transcript by definition), so making clone a rung
# rather than a sibling capability keeps "the strongest grant that matches
# the caller wins" well-defined when a direct grant and a group grant
# disagree. Replaces ADR-0213's owner/reader/actor/cloner conversation
# vocabulary, which is gone with conversation_memberships.
Role = Literal["read", "clone", "write", "admin"]

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, PoolTimeout

logger = logging.getLogger("agent_runtime.conversations")

# Same separate-PG*-variables convention as app/main.py's CHECKPOINT_PG* -
# a hand-built conninfo string never needs percent-encoding a generated
# password, unlike a postgresql:// URI would.
CONVERSATIONS_PGHOST = os.getenv("CONVERSATIONS_PGHOST", "")
CONVERSATIONS_PGPORT = os.getenv("CONVERSATIONS_PGPORT", "5432")
CONVERSATIONS_PGDATABASE = os.getenv("CONVERSATIONS_PGDATABASE", "")
CONVERSATIONS_PGUSER = os.getenv("CONVERSATIONS_PGUSER", "")
CONVERSATIONS_PGPASSWORD = os.getenv("CONVERSATIONS_PGPASSWORD", "")
CONVERSATIONS_PGSSLMODE = os.getenv("CONVERSATIONS_PGSSLMODE", "require")

# ADR-0212's own Decision SQL, applied idempotently at startup - same
# pattern as AsyncPostgresSaver.setup() for the checkpoint pool, hand
# written here since there's no dedicated .setup() for this schema.
_DDL = """
CREATE TABLE IF NOT EXISTS conversations (
    run_id        text        PRIMARY KEY,
    agent_name    text        NOT NULL,
    owner_sub     text        NOT NULL,
    title         text        NOT NULL DEFAULT '',
    project_id    text,
    source_run_id text        REFERENCES conversations(run_id),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    archived_at   timestamptz
);
CREATE INDEX IF NOT EXISTS ix_conversations_agent_owner ON conversations (agent_name, owner_sub);

CREATE TABLE IF NOT EXISTS conversation_stars (
    run_id     text        NOT NULL REFERENCES conversations(run_id),
    subject    text        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, subject)
);

-- ADR-0515: manual drag-reorder of the caller's own conversation list,
-- replacing the old implicit updated_at-DESC/starred-first ordering.
-- Nullable (no column-level NOT NULL) rather than a two-step ADD-then-
-- SET-NOT-NULL migration - every INSERT below always supplies a value,
-- and the backfill just after this ALTER clears every pre-existing NULL
-- in the same startup pass before the pool is ever handed to a request.
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS sort_order bigint;

-- Idempotent: only rows still NULL (pre-ADR-0515 conversations, or a
-- fresh row from a version-skewed replica before this ALTER lands there)
-- are touched - a rerun on an already-backfilled table is a no-op. Most
-- recently created gets the smallest sort_order (rn=1) so ascending
-- sort_order reproduces today's "most recent first" default exactly;
-- record_turn's INSERT below then keeps assigning new conversations a
-- value below the current minimum, so a brand new conversation always
-- lands above this reconstructed order too.
WITH ranked AS (
    SELECT run_id, row_number() OVER (
        PARTITION BY agent_name, owner_sub ORDER BY created_at DESC
    ) AS rn
    FROM conversations
    WHERE sort_order IS NULL
)
UPDATE conversations SET sort_order = ranked.rn
FROM ranked
WHERE conversations.run_id = ranked.run_id;

-- ADR-0512/WP-55: retained for one release. ADR-0528 stops writing this
-- column (the Salesforce stamp now lives on projects.salesforce_verified_at,
-- verified once per project rather than once per conversation); the
-- migration below clears it alongside any unverifiable project_id, and
-- dropping the column itself is deliberately a separate change.
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS project_id_verified_at timestamptz;

-- ADR-0527: the project is a first-class object and the source of truth
-- for project_id, which ADR-0209 left as a client-asserted string. No
-- owner column by design: the creator simply gets an 'admin' grant below,
-- and created_by is audit metadata that is NEVER an authorization input
-- (unlike conversations.owner_sub, which still is). An engagement
-- outlives whoever opened it, so the "project can never become
-- unadministrable" invariant is held by projects.save_project's
-- last-admin guard instead of by a single-owner column.
CREATE TABLE IF NOT EXISTS projects (
    project_id                text        PRIMARY KEY,
    title                     text        NOT NULL,
    context                   text        NOT NULL DEFAULT '',
    -- ADR-0034/0035: the classification the context inherits and every
    -- turn in this project escalates to, monotonically.
    classification            text        NOT NULL DEFAULT 'C2'
                                          CHECK (classification IN ('C1', 'C2', 'C3')),
    -- ADR-0528: set => "customer project", NULL => "free project". Never
    -- emitted in a header or a span - app/clients/model_router.py sends
    -- project_id, and only project_id.
    salesforce_opportunity_id text,
    salesforce_verified_at    timestamptz,
    -- ADR-0527: monotone counter the rag-project project_memberships
    -- projection is keyed on, so a late retry can never rewind it.
    grants_revision           bigint      NOT NULL DEFAULT 1,
    created_by                text        NOT NULL,
    created_at                timestamptz NOT NULL DEFAULT now(),
    updated_at                timestamptz NOT NULL DEFAULT now(),
    archived_at               timestamptz,
    CONSTRAINT ck_projects_context_length CHECK (char_length(context) <= 54000),
    CONSTRAINT ck_projects_salesforce_pair
        CHECK ((salesforce_opportunity_id IS NULL) = (salesforce_verified_at IS NULL))
);
CREATE INDEX IF NOT EXISTS ix_projects_live ON projects (project_id) WHERE archived_at IS NULL;

-- ADR-0527: four roles forming a total order (read < clone < write <
-- admin) granted to a Keycloak subject OR a business-role group. XOR, not
-- ADR-0209 project_memberships' inclusive OR: the RBAC tab renders one row
-- per grant under either a Users or a Groups subsection, and a row
-- carrying both would have no unambiguous home nor revoke semantics.
-- agent_* entitlement groups are refused as grant targets in Python
-- (app/projects.py's _business_role_groups) on both the write and the
-- resolution side - admitting them would collapse ADR-0040's two
-- dimensions into one.
CREATE TABLE IF NOT EXISTS project_grants (
    id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id  text        NOT NULL REFERENCES projects(project_id),
    subject     text,
    group_name  text,
    role        text        NOT NULL CHECK (role IN ('read', 'clone', 'write', 'admin')),
    granted_by  text        NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_project_grants_subject_xor_group
        CHECK ((subject IS NULL) <> (group_name IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_project_grants_subject
    ON project_grants (project_id, subject) WHERE subject IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_project_grants_group
    ON project_grants (project_id, group_name) WHERE group_name IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_project_grants_subject ON project_grants (subject) WHERE subject IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_project_grants_group ON project_grants (group_name) WHERE group_name IS NOT NULL;

-- ADR-0527: a star is one member's private organizing flag, not a
-- property of the project - the same reasoning ADR-0212 used to keep
-- conversation_stars out of the conversations row.
CREATE TABLE IF NOT EXISTS project_stars (
    project_id text        NOT NULL REFERENCES projects(project_id),
    subject    text        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, subject)
);

-- ADR-0527 migration. conversations.project_id was a free text field any
-- caller could set through ChatRequest (ADR-0209's "forwarded as-is, this
-- BFF does not validate project membership"). Anything with no projects
-- row was never verifiable and nothing consumed it beyond ADR-0512's
-- now-superseded per-conversation binding, so it is cleared. This MUST
-- run before the foreign key below: the DDL is fail-fast inside
-- pool_context(), so adding the constraint first would crash-loop the pod
-- on any database that still holds such a value.
DO $$
DECLARE orphans bigint;
BEGIN
    SELECT count(*) INTO orphans FROM conversations c
    WHERE c.project_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM projects p WHERE p.project_id = c.project_id);
    IF orphans > 0 THEN
        RAISE NOTICE 'ADR-0527: clearing % unverifiable conversations.project_id value(s)', orphans;
        UPDATE conversations c
        SET project_id = NULL, project_id_verified_at = NULL
        WHERE c.project_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM projects p WHERE p.project_id = c.project_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_conversations_project') THEN
        ALTER TABLE conversations
            ADD CONSTRAINT fk_conversations_project
            FOREIGN KEY (project_id) REFERENCES projects(project_id);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_conversations_project ON conversations (project_id) WHERE project_id IS NOT NULL;

-- ADR-0527 supersedes ADR-0213 in full: sharing moves from the
-- conversation to the project, so this table is dropped rather than
-- migrated. That is safe precisely because ADR-0213 was never provisioned
-- - GET /api/colleagues has always answered 503 for want of the
-- zuno-admin-api Keycloak client, so no grant was ever made in service.
-- The count is raised as a NOTICE anyway, so an operator sees any row
-- that somehow existed.
DO $$
DECLARE leftovers bigint;
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = 'conversation_memberships'
    ) THEN
        EXECUTE 'SELECT count(*) FROM conversation_memberships' INTO leftovers;
        RAISE NOTICE 'ADR-0527: dropping conversation_memberships (% row(s))', leftovers;
    END IF;
END $$;
DROP TABLE IF EXISTS conversation_memberships;

-- ADR-0213's one surviving clause: two collaborators must never race on
-- one LangGraph checkpoint thread. Project sharing creates that hazard
-- exactly as conversation sharing did, so the lease stays - now renewed
-- mid-stream, which ADR-0213 specified and its implementation omitted.
CREATE TABLE IF NOT EXISTS conversation_write_locks (
    run_id           text        PRIMARY KEY REFERENCES conversations(run_id),
    holder_sub       text        NOT NULL,
    acquired_at      timestamptz NOT NULL DEFAULT now(),
    lease_expires_at timestamptz NOT NULL
);
"""


def _conninfo() -> Optional[str]:
    """None when unconfigured - the caller (pool_context) then yields None,
    same "unset -> feature off" convention as app/main.py's
    _checkpoint_conninfo()."""
    if not (
        CONVERSATIONS_PGHOST and CONVERSATIONS_PGDATABASE and CONVERSATIONS_PGUSER and CONVERSATIONS_PGPASSWORD
    ):
        return None
    return (
        f"host={CONVERSATIONS_PGHOST} port={CONVERSATIONS_PGPORT} dbname={CONVERSATIONS_PGDATABASE} "
        f"user={CONVERSATIONS_PGUSER} password={CONVERSATIONS_PGPASSWORD} sslmode={CONVERSATIONS_PGSSLMODE}"
    )


@asynccontextmanager
async def pool_context() -> AsyncIterator[Optional[AsyncConnectionPool]]:
    """Called once from app/main.py's lifespan, wrapping its existing
    checkpoint-pool setup one level deeper. Yields an opened, DDL'd pool,
    or None if CONVERSATIONS_PG* is unset."""
    conninfo = _conninfo()
    if conninfo is None:
        logger.info("CONVERSATIONS_PG* not fully configured - conversation persistence disabled")
        yield None
        return

    async with AsyncConnectionPool(
        conninfo,
        min_size=1,
        max_size=int(os.getenv("CONVERSATIONS_POOL_MAX_SIZE", "10")),
        kwargs={"autocommit": True, "prepare_threshold": None, "row_factory": dict_row},
        # Same check=check_connection rationale as app/main.py's checkpoint
        # pool: a connection opened before a Patroni failover must be
        # probed and discarded before handout, never handed to a caller
        # already dead.
        check=AsyncConnectionPool.check_connection,
    ) as pool:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(_DDL)
        logger.info(
            "Conversation persistence enabled at %s:%s/%s",
            CONVERSATIONS_PGHOST, CONVERSATIONS_PGPORT, CONVERSATIONS_PGDATABASE,
        )
        yield pool


def _require_pool(pool: Optional[AsyncConnectionPool]) -> AsyncConnectionPool:
    """ADR-0212 Security considerations: list/transcript/resume must fail
    closed (503), never silently fall back to "no restriction", if this
    pool is unreachable. record_turn is the sole, deliberate exception -
    see this module's own docstring."""
    if pool is None:
        raise HTTPException(status_code=503, detail="conversation persistence is unavailable")
    return pool


def _derive_title(message: str, *, max_length: int = 60) -> str:
    text = " ".join(message.split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"


# ADR-0527: the SQL rank of each role, mirroring _ROLE_RANK in
# app/projects.py. Kept as an inline CASE rather than a PostgreSQL enum so
# the vocabulary lives in exactly one migration-free place (the CHECK
# constraint in _DDL) and adding a rung never needs a type migration.
_ROLE_RANK_SQL = "CASE g.role WHEN 'admin' THEN 4 WHEN 'write' THEN 3 WHEN 'clone' THEN 2 ELSE 1 END"

# ADR-0527's access rule as one reusable predicate over a `conversations c`
# alias: the caller's own conversation always qualifies (owner_sub still
# grants write on what you started, which is what makes the `clone` role
# useful rather than merely archival), otherwise a live project grant of
# at least min_rank does. A conversation with no project and no ownership
# match satisfies neither branch, so it stays private - fail closed by
# construction rather than by a separate check the caller might forget.
_ACCESS_PREDICATE = f"""(
    c.owner_sub = %(subject)s
    OR EXISTS (
        SELECT 1 FROM projects p
        JOIN project_grants g ON g.project_id = p.project_id
        WHERE p.project_id = c.project_id
          AND p.archived_at IS NULL
          AND (g.subject = %(subject)s OR g.group_name = ANY(%(groups)s::text[]))
          AND {_ROLE_RANK_SQL} >= %(min_rank)s
    )
)"""

ROLE_RANK = {"read": 1, "clone": 2, "write": 3, "admin": 4}


def rank_of(role: Optional[str]) -> int:
    """0 for "no role at all" - the fail-closed floor every rank
    comparison in this module and app/projects.py comes back to."""
    return ROLE_RANK.get(role or "", 0)


async def record_turn(
    pool: Optional[AsyncConnectionPool],
    *,
    run_id: str,
    agent_name: str,
    owner_sub: str,
    opening_message: str,
    project_id: Optional[str] = None,
) -> None:
    """Called from app/main.py's agent_chat right after _resolve_run_id -
    inserts a new conversations row on first use of run_id (title derived
    from opening_message), or just bumps updated_at on resume (title is
    deliberately left untouched by the ON CONFLICT branch: a rename must
    survive later turns). Silently no-ops when pool is None, and also when
    a configured pool can't hand out a connection in time (PoolTimeout) or
    hands back one that's already dead (OperationalError) - unlike every
    other function in this module - see this module's own docstring for
    why record_turn alone must not fail closed. A live-cluster incident
    (2026-08-21: repeated PoolTimeouts under concurrent multi-agent load,
    single agent-runtime replica) showed this pool can genuinely time out
    transiently; since this call is incidental bookkeeping bolted onto the
    hot /chat path (app/main.py's agent_chat), not something the caller
    asked for, it must degrade the same way an unconfigured pool already
    does rather than 500 the whole chat reply over a missed metadata row.

    project_id (ADR-0527): the SERVER-RESOLVED project this conversation
    belongs to - app/main.py's agent_chat verifies the caller holds a grant
    on it before calling, and ADR-0527 removed the client-asserted value
    from _initial_state entirely. Only ever honoured on the INSERT branch:
    a conversation's project is fixed when it is created, so the ON
    CONFLICT branch deliberately leaves project_id alone rather than
    letting a later turn move a conversation between projects (which would
    silently move it between two different ACLs).

    Security note (ADR-0527): because this function swallows pool errors,
    a swallowed INSERT leaves a LangGraph checkpoint with no conversations
    row. resolve_access below returns None for that state, so the next
    access is DENIED - never treated as "no project restriction". That
    asymmetry is deliberate: losing a metadata row must cost visibility,
    never authorization."""
    if pool is None:
        return
    title = _derive_title(opening_message)
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO conversations (
                        run_id, agent_name, owner_sub, title, sort_order, project_id
                    )
                    VALUES (
                        %(run_id)s, %(agent_name)s, %(owner_sub)s, %(title)s,
                        COALESCE(
                            (SELECT MIN(sort_order) FROM conversations
                             WHERE agent_name = %(agent_name)s AND owner_sub = %(owner_sub)s),
                            1
                        ) - 1,
                        %(project_id)s::text
                    )
                    ON CONFLICT (run_id) DO UPDATE SET updated_at = now()
                    """,
                    {
                        "run_id": run_id,
                        "agent_name": agent_name,
                        "owner_sub": owner_sub,
                        "title": title,
                        "project_id": project_id,
                    },
                )
    except (PoolTimeout, psycopg.OperationalError) as exc:
        logger.warning(
            "conversations pool unavailable, skipping metadata write: run_id=%s agent=%s: %s",
            run_id, agent_name, exc,
        )


async def resolve_owner(pool: Optional[AsyncConnectionPool], run_id: str) -> Optional[str]:
    """The conversations table's owner_sub for run_id, or None if no row
    exists yet (a pre-ADR-0212 checkpoint - additive, no backfill, per
    that ADR's Operational considerations). Callers that need the
    graceful "feature not configured" degrade (app/main.py's
    _resolve_run_id) must guard the call themselves with `pool is not
    None` - this function itself fails closed (503) on a None pool, same
    as every other function here besides record_turn."""
    pool = _require_pool(pool)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT owner_sub FROM conversations WHERE run_id = %s", (run_id,))
            row = await cur.fetchone()
    return row["owner_sub"] if row else None


async def resolve_access(
    pool: Optional[AsyncConnectionPool],
    *,
    run_id: str,
    subject: str,
    groups: List[str],
) -> Optional[Dict[str, Any]]:
    """ADR-0527's single access check, replacing ADR-0213's get_role. One
    statement and one round trip: the conversation, its project, and the
    caller's strongest matching grant, resolved together by a lateral join
    rather than by three sequential queries on the hot /chat path.

    Returns None - the fail-closed denial every caller must act on - when
    the run_id has no conversations row at all (including the swallowed-
    write case record_turn documents), when the conversation is private to
    someone else, or when its project is archived or ungranted. Never
    guesses a default role.

    On success the dict carries `role` (the caller's effective role on
    THIS conversation, already accounting for ownership) plus the project
    fields agent_chat needs for context injection and ADR-0528's customer-
    project check, so no caller ever needs a second query.
    """
    pool = _require_pool(pool)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"""
                SELECT c.owner_sub, c.agent_name, c.project_id, c.archived_at,
                       p.title AS project_title,
                       p.context AS project_context,
                       p.classification AS project_classification,
                       p.salesforce_opportunity_id IS NOT NULL AS is_customer,
                       p.salesforce_verified_at,
                       p.archived_at AS project_archived_at,
                       g.role AS project_role
                FROM conversations c
                LEFT JOIN projects p
                       ON p.project_id = c.project_id AND p.archived_at IS NULL
                LEFT JOIN LATERAL (
                    SELECT g.role FROM project_grants g
                    WHERE g.project_id = p.project_id
                      AND (g.subject = %(subject)s OR g.group_name = ANY(%(groups)s::text[]))
                    ORDER BY {_ROLE_RANK_SQL} DESC
                    LIMIT 1
                ) g ON TRUE
                WHERE c.run_id = %(run_id)s
                """,
                {"run_id": run_id, "subject": subject, "groups": list(groups)},
            )
            row = await cur.fetchone()

    if row is None:
        return None

    project_role = row["project_role"]
    if row["owner_sub"] == subject:
        # You may always write your own conversation, whatever your project
        # role - ADR-0527 clause 3. An owner who is also a project admin
        # keeps the stronger role so they retain the admin-only actions.
        role: Optional[str] = "admin" if project_role == "admin" else "write"
    elif project_role is None:
        # Either no project (private to its owner) or no grant on it.
        return None
    else:
        role = project_role

    return {
        "role": role,
        "owner_sub": row["owner_sub"],
        "agent_name": row["agent_name"],
        "archived_at": row["archived_at"],
        "project_id": row["project_id"],
        "project_title": row["project_title"],
        "project_context": row["project_context"] or "",
        "project_classification": row["project_classification"],
        "is_customer": bool(row["is_customer"]),
        "salesforce_verified_at": row["salesforce_verified_at"],
    }


async def list_conversations(
    pool: Optional[AsyncConnectionPool],
    *,
    agent_name: str,
    subject: str,
    groups: List[str],
    starred_only: bool = False,
) -> List[Dict[str, Any]]:
    """ADR-0527 widens ADR-0212's owner-only list to two disjoint blocks,
    both still scoped to this agent (a project is cross-agent, but a
    sidebar is not - ADR-0527 clause 6):

    1. the caller's own conversations that belong to no project, and
    2. every live conversation of every live project the caller holds a
       grant on - including conversations owned by colleagues, which is
       the whole point of a shared project.

    This is the single most security-sensitive query in the module: it
    moved from one owner_sub predicate to a membership join, and a mistake
    here leaks colleagues' conversations. tests/test_conversations.py's
    test_list_conversations_covers_every_shape_adr_0527_enumerates covers
    all five shapes ADR-0527's Security considerations enumerate, against a
    fixture that replays this query's own join and WHERE clauses.

    Each row carries project_id and the caller's effective role so the
    frontend can group the list and decide read-only mode without a second
    call.
    """
    pool = _require_pool(pool)
    query = f"""
        SELECT c.run_id, c.title, c.updated_at, c.project_id,
               (s.run_id IS NOT NULL) AS starred,
               (c.owner_sub = %(subject)s) AS owned,
               g.role AS project_role
        FROM conversations c
        LEFT JOIN conversation_stars s
               ON s.run_id = c.run_id AND s.subject = %(subject)s
        LEFT JOIN projects p
               ON p.project_id = c.project_id AND p.archived_at IS NULL
        LEFT JOIN LATERAL (
            SELECT g.role FROM project_grants g
            WHERE g.project_id = p.project_id
              AND (g.subject = %(subject)s OR g.group_name = ANY(%(groups)s::text[]))
            ORDER BY {_ROLE_RANK_SQL} DESC
            LIMIT 1
        ) g ON TRUE
        WHERE c.agent_name = %(agent_name)s
          AND c.archived_at IS NULL
          AND (
                (c.project_id IS NULL AND c.owner_sub = %(subject)s)
                OR (p.project_id IS NOT NULL AND g.role IS NOT NULL)
              )
    """
    if starred_only:
        query += " AND s.run_id IS NOT NULL"
    # ADR-0515: the list's own order is the caller's manual drag-reorder
    # (sort_order), not an automatic starred-first rule - starred is still
    # returned per row, but only drives ordering of the *open in-app tabs*
    # client-side (chat/Chat.tsx), a separate concern. updated_at DESC only
    # breaks ties among rows that still share a sort_order.
    query += " ORDER BY COALESCE(c.sort_order, 9223372036854775807) ASC, c.updated_at DESC"

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                query,
                {"agent_name": agent_name, "subject": subject, "groups": list(groups)},
            )
            rows = await cur.fetchall()
    return [
        {
            "run_id": r["run_id"],
            "title": r["title"],
            "updated_at": r["updated_at"].isoformat(),
            "starred": r["starred"],
            "project_id": r["project_id"],
            # Ownership wins for the same reason it does in resolve_access.
            "role": ("admin" if r["project_role"] == "admin" else "write") if r["owned"] else r["project_role"],
        }
        for r in rows
    ]


async def archive_conversation(
    pool: Optional[AsyncConnectionPool], *, run_id: str, subject: str, groups: List[str]
) -> bool:
    """Soft-delete: hides the conversation from list_conversations (which
    already filters archived_at IS NULL) without touching the underlying
    LangGraph checkpoint - the message history itself is never deleted,
    only this metadata row's visibility.

    ADR-0527 clause 4 widens this from owner-only to "the owner, or a
    project admin" - a project admin already holds cascade archival over
    the whole project, so withholding it per-conversation would be
    arbitrary. It stops short of the irreversible purge, which stays
    owner-only. Returns False (the caller maps this to a 404) for an
    unknown run_id, an insufficient role, or an already-archived row
    alike - collapsed to one case so this endpoint never confirms that
    another subject's run_id exists at all."""
    pool = _require_pool(pool)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"""
                UPDATE conversations c SET archived_at = now()
                WHERE c.run_id = %(run_id)s AND c.archived_at IS NULL AND {_ACCESS_PREDICATE}
                """,
                {"run_id": run_id, "subject": subject, "groups": list(groups),
                 "min_rank": ROLE_RANK["admin"]},
            )
            return cur.rowcount > 0


async def rename_conversation(
    pool: Optional[AsyncConnectionPool], *, run_id: str, subject: str, groups: List[str], title: str
) -> bool:
    """ADR-0527 clause 4: the conversation's owner, or a project `write`
    member. Same "collapsed to one not-found case" rationale as
    archive_conversation."""
    pool = _require_pool(pool)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"""
                UPDATE conversations c SET title = %(title)s, updated_at = now()
                WHERE c.run_id = %(run_id)s AND {_ACCESS_PREDICATE}
                """,
                {"title": title, "run_id": run_id, "subject": subject, "groups": list(groups),
                 "min_rank": ROLE_RANK["write"]},
            )
            return cur.rowcount > 0


async def set_star(
    pool: Optional[AsyncConnectionPool], *, run_id: str, subject: str, groups: List[str], starred: bool
) -> bool:
    """Toggles the caller's personal star. ADR-0527 clause 4 makes this
    available to anyone who may READ the conversation, not just its owner:
    a star is one member's private organizing flag over what they can see,
    and a shared project is exactly the case where organizing someone
    else's conversation is legitimate."""
    pool = _require_pool(pool)
    params = {"run_id": run_id, "subject": subject, "groups": list(groups), "min_rank": ROLE_RANK["read"]}
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"SELECT 1 FROM conversations c WHERE c.run_id = %(run_id)s AND {_ACCESS_PREDICATE}",
                params,
            )
            if await cur.fetchone() is None:
                return False
            if starred:
                await cur.execute(
                    "INSERT INTO conversation_stars (run_id, subject) VALUES (%s, %s) "
                    "ON CONFLICT (run_id, subject) DO NOTHING",
                    (run_id, subject),
                )
            else:
                await cur.execute(
                    "DELETE FROM conversation_stars WHERE run_id = %s AND subject = %s", (run_id, subject)
                )
    return True


async def reorder_conversations(
    pool: Optional[AsyncConnectionPool], *, agent_name: str, owner_sub: str, run_ids: List[str]
) -> int:
    """ADR-0515: persists a drag-drop reorder as an explicit sort_order per
    conversation, ascending - index 0 sorts first (list_conversations'
    ORDER BY). Scoped to (agent_name, owner_sub), the same per-user/
    per-agent boundary every other function in this module enforces; a
    run_id absent from that scope (wrong owner, wrong agent, or simply
    stale/unknown - e.g. a client racing a delete against a reorder) is
    silently skipped rather than failing the whole request. Returns the
    count actually updated so the caller can detect a stale client list."""
    pool = _require_pool(pool)
    updated = 0
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            for position, run_id in enumerate(run_ids):
                await cur.execute(
                    "UPDATE conversations SET sort_order = %s WHERE run_id = %s AND agent_name = %s AND owner_sub = %s",
                    (position, run_id, agent_name, owner_sub),
                )
                updated += cur.rowcount
    return updated


async def hard_delete_conversation(pool: Optional[AsyncConnectionPool], *, run_id: str, owner_sub: str) -> bool:
    """ADR-0515: irreversible - unlike archive_conversation's archived_at
    soft-hide, this purges the conversations row (and its
    conversation_stars rows) outright. Does not touch the LangGraph
    checkpoint itself - that lives in a separate pool this module
    deliberately never opens (see module docstring); app/main.py's
    hard_delete_conversation_endpoint purges it separately via
    graph.checkpointer.adelete_thread once this call confirms ownership.
    A SELECT-then-delete (not a bare DELETE ... RETURNING) because
    conversation_stars.run_id REFERENCES conversations(run_id) with no
    ON DELETE CASCADE - stars must be cleared first or the conversations
    DELETE below would violate that FK constraint. Same "collapsed to one
    not-found case" rationale as rename_conversation/archive_conversation."""
    pool = _require_pool(pool)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT 1 FROM conversations WHERE run_id = %s AND owner_sub = %s", (run_id, owner_sub)
            )
            if await cur.fetchone() is None:
                return False
            await cur.execute("DELETE FROM conversation_stars WHERE run_id = %s", (run_id,))
            await cur.execute("DELETE FROM conversations WHERE run_id = %s AND owner_sub = %s", (run_id, owner_sub))
    return True


def _derive_clone_title(title: str, *, max_length: int = 200) -> str:
    """ADR-0527 clause 4: a clone stays in its source project, so it needs
    a name that distinguishes it in the same list. "Foo" -> "Foo (copy)",
    "Foo (copy)" -> "Foo (copy 2)", "Foo (copy 7)" -> "Foo (copy 8)".
    Truncates to the same 200-character ceiling app/schemas.py enforces on
    a rename, so cloning a maximal title can never produce a row the
    rename endpoint would refuse."""
    base = title or "Untitled conversation"
    match = re.fullmatch(r"(?P<stem>.*) \(copy(?: (?P<n>\d+))?\)", base)
    if match:
        stem = match.group("stem")
        nth = int(match.group("n") or 1) + 1
        suffix = f" (copy {nth})"
    else:
        stem = base
        suffix = " (copy)"
    room = max_length - len(suffix)
    if len(stem) > room:
        stem = stem[: room - 1].rstrip() + "\u2026"
    return stem + suffix


async def clone_conversation(
    pool: Optional[AsyncConnectionPool],
    *,
    source_run_id: str,
    new_run_id: str,
    owner_sub: str,
) -> Optional[str]:
    """ADR-0527 clause 4: the clone stays in the SOURCE's project (ADR-0213
    made it a brand-new independently-owned conversation with no project;
    that is what changed) and takes a derived title. The cloner becomes
    owner_sub, which is precisely what makes the `clone` role useful: they
    may write to their own copy while remaining unable to write to the
    original. Grants are untouched - the project's RBAC already covers the
    copy, and nothing is reset.

    agent_name, project_id and title are copied from the source row by a
    correlated INSERT...SELECT so the caller needs no prior fetch. The
    caller (app/main.py's clone endpoint) copies the LangGraph
    checkpoint's channel_values into new_run_id's thread separately - this
    module never opens that pool (module docstring). sort_order follows
    record_turn's convention: the copy lands at the top of the cloner's
    own list.

    Returns the new title, or None if source_run_id no longer exists (the
    caller already checked a role against it, so this only loses a race
    with a delete)."""
    pool = _require_pool(pool)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT title FROM conversations WHERE run_id = %s", (source_run_id,))
            source = await cur.fetchone()
            if source is None:
                return None
            new_title = _derive_clone_title(source["title"])
            await cur.execute(
                """
                INSERT INTO conversations (
                    run_id, agent_name, owner_sub, title, source_run_id, project_id, sort_order
                )
                SELECT
                    %(new_run_id)s, c.agent_name, %(owner_sub)s, %(new_title)s,
                    %(source_run_id)s, c.project_id,
                    COALESCE(
                        (SELECT MIN(sort_order) FROM conversations
                         WHERE agent_name = c.agent_name AND owner_sub = %(owner_sub)s),
                        1
                    ) - 1
                FROM conversations c WHERE c.run_id = %(source_run_id)s
                """,
                {
                    "new_run_id": new_run_id,
                    "owner_sub": owner_sub,
                    "new_title": new_title,
                    "source_run_id": source_run_id,
                },
            )
            return new_title if cur.rowcount > 0 else None


_WRITE_LOCK_TTL_SECONDS = 30


async def acquire_write_lock(pool: Optional[AsyncConnectionPool], *, run_id: str, holder_sub: str) -> bool:
    """ADR-0213: single-active-writer lease. Like record_turn, this is
    one of the two functions in this module that must not fail closed on
    a None pool - chat itself must keep working when conversation
    persistence isn't configured, and without it there is no
    conversation_memberships row anyone else could hold to even contend
    for this lock, so an unconfigured pool trivially always "acquires"
    (True).

    The UPDATE...WHERE guards against silently stealing a still-live
    lease out from under its legitimate holder; it also lets the SAME
    holder renew their own lease (the `OR holder_sub = EXCLUDED.holder_sub`
    branch), which _stream_chat needs to do repeatedly while a reply
    streams. Returns False (the caller maps this to 409) when someone
    else already holds a live lease."""
    if pool is None:
        return True
    pool = _require_pool(pool)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO conversation_write_locks (run_id, holder_sub, acquired_at, lease_expires_at)
                VALUES (%(run_id)s, %(holder_sub)s, now(), now() + make_interval(secs => %(ttl)s))
                ON CONFLICT (run_id) DO UPDATE SET
                    holder_sub = EXCLUDED.holder_sub,
                    acquired_at = EXCLUDED.acquired_at,
                    lease_expires_at = EXCLUDED.lease_expires_at
                WHERE conversation_write_locks.lease_expires_at < now()
                   OR conversation_write_locks.holder_sub = EXCLUDED.holder_sub
                """,
                {"run_id": run_id, "holder_sub": holder_sub, "ttl": _WRITE_LOCK_TTL_SECONDS},
            )
            return cur.rowcount > 0


async def release_write_lock(pool: Optional[AsyncConnectionPool], *, run_id: str, holder_sub: str) -> None:
    """ADR-0213: released in the chat endpoint's finally/disconnect
    handler; the lease TTL is the fallback for a hard crash that skips
    this. Scoped to holder_sub so a lease already stolen by someone else
    (this holder's own lease expired first) is never released out from
    under its new legitimate holder. No-ops on an unconfigured pool, same
    as acquire_write_lock above - nothing to release."""
    if pool is None:
        return
    pool = _require_pool(pool)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM conversation_write_locks WHERE run_id = %s AND holder_sub = %s",
                (run_id, holder_sub),
            )
