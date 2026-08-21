"""ADR-0212: persistent conversation metadata (conversations,
conversation_stars) on a dedicated Postgres pool - deliberately separate
from ADR-0103's checkpoint pool (app/main.py), never sharing a connection
or credential with it (ADR-0212 Security considerations).

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
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import HTTPException
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

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


async def record_turn(
    pool: Optional[AsyncConnectionPool],
    *,
    run_id: str,
    agent_name: str,
    owner_sub: str,
    opening_message: str,
) -> None:
    """Called from app/main.py's agent_chat right after _resolve_run_id -
    inserts a new conversations row on first use of run_id (title derived
    from opening_message), or just bumps updated_at on resume (title is
    deliberately left untouched by the ON CONFLICT branch: a rename must
    survive later turns). Silently no-ops when pool is None, unlike every
    other function in this module - see this module's own docstring for
    why record_turn alone must not fail closed."""
    if pool is None:
        return
    title = _derive_title(opening_message)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO conversations (run_id, agent_name, owner_sub, title, sort_order)
                VALUES (
                    %(run_id)s, %(agent_name)s, %(owner_sub)s, %(title)s,
                    COALESCE(
                        (SELECT MIN(sort_order) FROM conversations
                         WHERE agent_name = %(agent_name)s AND owner_sub = %(owner_sub)s),
                        1
                    ) - 1
                )
                ON CONFLICT (run_id) DO UPDATE SET updated_at = now()
                """,
                {"run_id": run_id, "agent_name": agent_name, "owner_sub": owner_sub, "title": title},
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


async def list_conversations(
    pool: Optional[AsyncConnectionPool],
    *,
    agent_name: str,
    owner_sub: str,
    starred_only: bool = False,
) -> List[Dict[str, Any]]:
    pool = _require_pool(pool)
    query = """
        SELECT c.run_id, c.title, c.updated_at, (s.run_id IS NOT NULL) AS starred
        FROM conversations c
        LEFT JOIN conversation_stars s ON s.run_id = c.run_id AND s.subject = %(owner_sub)s
        WHERE c.agent_name = %(agent_name)s AND c.owner_sub = %(owner_sub)s AND c.archived_at IS NULL
    """
    if starred_only:
        query += " AND s.run_id IS NOT NULL"
    # ADR-0515: the list's own order is now the caller's manual
    # drag-reorder (sort_order), not an automatic starred-first rule -
    # starred is still returned per row, but only drives ordering of the
    # *open in-app tabs* client-side (chat/Chat.tsx), a separate concern.
    # updated_at DESC only breaks ties among rows that still share a
    # sort_order (never happens through this module's own writers, but
    # keeps the order deterministic against any future direct SQL).
    query += " ORDER BY COALESCE(c.sort_order, 9223372036854775807) ASC, c.updated_at DESC"

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, {"agent_name": agent_name, "owner_sub": owner_sub})
            rows = await cur.fetchall()
    return [
        {
            "run_id": r["run_id"],
            "title": r["title"],
            "updated_at": r["updated_at"].isoformat(),
            "starred": r["starred"],
        }
        for r in rows
    ]


async def archive_conversation(pool: Optional[AsyncConnectionPool], *, run_id: str, owner_sub: str) -> bool:
    """Soft-delete: hides the conversation from list_conversations (which
    already filters archived_at IS NULL) without touching the underlying
    LangGraph checkpoint - the message history itself is never deleted,
    only this metadata row's visibility. Same "collapsed to one
    not-found case" rationale as rename_conversation/set_star. Guards
    `archived_at IS NULL` in the WHERE clause so re-archiving an already
    archived conversation reports not-found rather than silently
    bumping nothing."""
    pool = _require_pool(pool)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE conversations SET archived_at = now() WHERE run_id = %s AND owner_sub = %s AND archived_at IS NULL",
                (run_id, owner_sub),
            )
            return cur.rowcount > 0


async def rename_conversation(
    pool: Optional[AsyncConnectionPool], *, run_id: str, owner_sub: str, title: str
) -> bool:
    """Returns False (the caller maps this to a 404) for either an unknown
    run_id or one owned by a different subject - collapsed to a single
    case, unlike _resolve_run_id's 404/403 split, so this endpoint never
    confirms that another subject's run_id exists at all."""
    pool = _require_pool(pool)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE conversations SET title = %s, updated_at = now() WHERE run_id = %s AND owner_sub = %s",
                (title, run_id, owner_sub),
            )
            return cur.rowcount > 0


async def set_star(pool: Optional[AsyncConnectionPool], *, run_id: str, owner_sub: str, starred: bool) -> bool:
    """Toggles the caller's personal star. Same "collapsed to one not-found
    case" rationale as rename_conversation."""
    pool = _require_pool(pool)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT 1 FROM conversations WHERE run_id = %s AND owner_sub = %s", (run_id, owner_sub)
            )
            if await cur.fetchone() is None:
                return False
            if starred:
                await cur.execute(
                    "INSERT INTO conversation_stars (run_id, subject) VALUES (%s, %s) "
                    "ON CONFLICT (run_id, subject) DO NOTHING",
                    (run_id, owner_sub),
                )
            else:
                await cur.execute(
                    "DELETE FROM conversation_stars WHERE run_id = %s AND subject = %s", (run_id, owner_sub)
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
