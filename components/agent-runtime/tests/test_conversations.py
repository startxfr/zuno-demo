#!/usr/bin/env python3
"""ADR-0212 tests for app/conversations.py and the _resolve_run_id
ownership-check widening in app/main.py.

Same philosophy as tests/test_checkpointing.py: this sandbox has no live
Postgres, so these tests prove what's provable without one - the pure
title-derivation/conninfo-building logic, the pool_context()
unconfigured-degrade path, and every function's fail-closed 503 when
handed a None pool (the meaningful security-negative proof: a caller
that forgot to configure CONVERSATIONS_PG*, or hit it while genuinely
down, gets a hard failure, never a silent "no restriction").

ADR-0527's two access-resolution paths - resolve_access's effective role
and the rewritten listing's visibility - are exercised against a stub
psycopg pool (the _StubPool/_StubCursor pair below, the same fake-cursor
shape tests/test_projects.py already uses, plus the pool layer), never
recomputed in a test body: the listing fixture answers the query the
function actually emitted, so the visibility rule has exactly one
definition and it lives in app/conversations.py. The real
SQL/DDL against a live agent-conversations database is exercised
separately against the actual cluster, the same "deferred to production"
split test_checkpointing.py's own docstring documents for the checkpoint
pool.

Run directly:

    cd components/agent-runtime && python3 tests/test_conversations.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import re
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))

from fastapi import HTTPException  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from psycopg_pool import PoolTimeout  # noqa: E402

import app.conversations as conversations_module  # noqa: E402
from app.auth import CallerIdentity  # noqa: E402
from app.conversations import (  # noqa: E402
    _conninfo,
    _derive_title,
    acquire_write_lock,
    archive_conversation,
    _derive_clone_title,
    clone_conversation,
    hard_delete_conversation,
    list_conversations,
    pool_context,
    release_write_lock,
    rename_conversation,
    reorder_conversations,
    resolve_access,
    resolve_owner,
    set_star,
)
from app.graph.nodes import _ANSWER_TASK, _TEKOS  # noqa: E402
from app.graph.shapes.retrieve_reason_respond import build as _build  # noqa: E402
from app.main import _resolve_run_id  # noqa: E402
from app.schemas import ChatRequest  # noqa: E402


def build_graph(checkpointer):
    return _build(checkpointer, _TEKOS, _ANSWER_TASK)


def _identity(sub: str) -> CallerIdentity:
    return CallerIdentity(sub=sub, groups=["consultant"], raw_claims={}, token="fake-token")


def _patch_env(**values):
    saved = {
        "CONVERSATIONS_PGHOST": conversations_module.CONVERSATIONS_PGHOST,
        "CONVERSATIONS_PGPORT": conversations_module.CONVERSATIONS_PGPORT,
        "CONVERSATIONS_PGDATABASE": conversations_module.CONVERSATIONS_PGDATABASE,
        "CONVERSATIONS_PGUSER": conversations_module.CONVERSATIONS_PGUSER,
        "CONVERSATIONS_PGPASSWORD": conversations_module.CONVERSATIONS_PGPASSWORD,
        "CONVERSATIONS_PGSSLMODE": conversations_module.CONVERSATIONS_PGSSLMODE,
    }
    for key, value in values.items():
        setattr(conversations_module, key, value)
    return saved


def _restore_env(saved: dict) -> None:
    for key, value in saved.items():
        setattr(conversations_module, key, value)


async def test_conninfo_is_none_when_unconfigured() -> None:
    """Incident 2026-08-14-style regression, same rationale as
    test_checkpointing.py's own equivalent test: unset CONVERSATIONS_PG*
    must degrade cleanly (None), never a partial/broken conninfo string."""
    saved = _patch_env(
        CONVERSATIONS_PGHOST="",
        CONVERSATIONS_PGDATABASE="agent-conversations",
        CONVERSATIONS_PGUSER="agentconversations",
        CONVERSATIONS_PGPASSWORD="secret",
    )
    try:
        assert _conninfo() is None
    finally:
        _restore_env(saved)


async def test_conninfo_includes_sslmode_and_dbname() -> None:
    saved = _patch_env(
        CONVERSATIONS_PGHOST="zuno-postgresql-pgbouncer.zuno-data.svc.cluster.local",
        CONVERSATIONS_PGPORT="5432",
        CONVERSATIONS_PGDATABASE="agent-conversations",
        CONVERSATIONS_PGUSER="agentconversations",
        CONVERSATIONS_PGPASSWORD="secret",
        CONVERSATIONS_PGSSLMODE="require",
    )
    try:
        conninfo = _conninfo()
        assert conninfo is not None
        assert "sslmode=require" in conninfo
        assert "dbname=agent-conversations" in conninfo
        assert "user=agentconversations" in conninfo
    finally:
        _restore_env(saved)


async def test_pool_context_yields_none_when_unconfigured() -> None:
    """The unconfigured-degrade path is provable without a live DB - this
    is the exact branch every CI run (no CONVERSATIONS_PG*) exercises."""
    saved = _patch_env(CONVERSATIONS_PGHOST="", CONVERSATIONS_PGDATABASE="", CONVERSATIONS_PGUSER="", CONVERSATIONS_PGPASSWORD="")
    try:
        async with pool_context() as pool:
            assert pool is None
    finally:
        _restore_env(saved)


async def test_derive_title_uses_the_message_as_is_when_short() -> None:
    assert _derive_title("How do I configure OpenShift AI?") == "How do I configure OpenShift AI?"


async def test_derive_title_collapses_whitespace() -> None:
    assert _derive_title("  hello   world  \n") == "hello world"


async def test_derive_title_truncates_long_messages_with_ellipsis() -> None:
    message = "x" * 100
    title = _derive_title(message, max_length=60)
    assert len(title) == 60
    assert title.endswith("…")


async def _expect_503(coro) -> None:
    try:
        await coro
        raise AssertionError("expected an HTTPException(503) for a None pool")
    except HTTPException as exc:
        assert exc.status_code == 503, exc


async def test_resolve_owner_fails_closed_on_a_none_pool() -> None:
    """ADR-0212 Security considerations: list/transcript/resume must fail
    closed (503), never silently proceed unrestricted, if the pool is
    unreachable/unconfigured."""
    await _expect_503(resolve_owner(None, "run-abc"))


async def test_list_conversations_fails_closed_on_a_none_pool() -> None:
    await _expect_503(list_conversations(None, agent_name="tekos", subject="alice", groups=["consultant"]))


async def test_rename_conversation_fails_closed_on_a_none_pool() -> None:
    await _expect_503(rename_conversation(None, run_id="run-abc", subject="alice", groups=[], title="New title"))


async def test_set_star_fails_closed_on_a_none_pool() -> None:
    await _expect_503(set_star(None, run_id="run-abc", subject="alice", groups=[], starred=True))


async def test_archive_conversation_fails_closed_on_a_none_pool() -> None:
    await _expect_503(archive_conversation(None, run_id="run-abc", subject="alice", groups=[]))


async def test_reorder_conversations_fails_closed_on_a_none_pool() -> None:
    """ADR-0515: same fail-closed posture as every other writer in this
    module besides record_turn."""
    await _expect_503(reorder_conversations(None, agent_name="tekos", owner_sub="alice", run_ids=["run-abc"]))


async def test_hard_delete_conversation_fails_closed_on_a_none_pool() -> None:
    """ADR-0515: same fail-closed posture as archive_conversation - an
    irreversible operation must never silently proceed unrestricted."""
    await _expect_503(hard_delete_conversation(None, run_id="run-abc", owner_sub="alice"))


async def test_resolve_access_fails_closed_on_a_none_pool() -> None:
    """ADR-0527: the single access check inherits ADR-0213's posture - a
    caller must never treat "pool unreachable" as "no role, but proceed
    anyway". This is the one function every read and write path in
    app/main.py now goes through, so its fail-closed behaviour is the
    whole module's."""
    await _expect_503(resolve_access(None, run_id="run-abc", subject="alice", groups=["consultant"]))


# --------------------------------------------------------------------------
# ADR-0527 criterion 10: the two access-resolution paths, exercised against a
# stub psycopg pool instead of being recomputed in the test body
# --------------------------------------------------------------------------


class _StubCursor:
    """The same shape as tests/test_projects.py's _FakeCursor (async context
    manager, execute/fetchone/fetchall), except the rows come from an
    `answer(query, params)` callable - so a test can stand in for the
    agent-conversations database rather than for one canned reply, and can
    see the SQL and the bound parameters the function under test actually
    sent."""

    def __init__(self, answer):
        self._answer = answer
        self._rows = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, query, params=None):
        self._rows = self._answer(query, dict(params or {}))

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return list(self._rows)


class _StubConn:
    def __init__(self, answer):
        self._answer = answer

    def cursor(self):
        return _StubCursor(self._answer)


class _StubPool:
    """The pool layer test_projects.py's fakes stop short of: pool.connection()
    is the async context manager every function in app/conversations.py opens
    before it touches a cursor."""

    def __init__(self, answer):
        self._answer = answer

    @asynccontextmanager
    async def connection(self):
        yield _StubConn(self._answer)


def _conversation_row(*, owner_sub: str, project_role):
    """One row of resolve_access's SELECT list exactly as psycopg's dict_row
    hands it back: a live conversation in a live project, so the only things
    varying case to case are who owns it and what grant the caller holds."""
    return {
        "owner_sub": owner_sub,
        "agent_name": "tekos",
        "project_id": "proj-shared",
        "archived_at": None,
        "project_title": "Acme migration",
        "project_context": "",
        "project_classification": "internal",
        "is_customer": False,
        "salesforce_verified_at": None,
        "project_archived_at": None,
        "project_role": project_role,
    }


async def test_owner_always_outranks_a_weaker_project_role() -> None:
    """ADR-0527 clause 3: owner_sub keeps granting write on your own
    conversation whatever your project role - that is precisely what makes
    the `clone` role useful (fork and continue) rather than merely
    archival. An owner who is ALSO a project admin keeps the stronger
    role, so they do not lose the admin-only actions by owning the row.

    Proved by calling resolve_access itself against a stub pool, never by
    recomputing the rule here: each project role is resolved twice off the
    same row, once for the owner and once for a colleague. "Outranks" is a
    claim about ownership, so the colleague's resolution (exactly the
    project role, and a flat denial with no grant at all) is what gives the
    owner's resolution its meaning - and a resolver that returned a
    constant, or that guessed a default role for the no-grant case, fails
    one half or the other."""
    for project_role, owner_expected, colleague_expected in [
        (None, "write", None),
        ("read", "write", "read"),
        ("clone", "write", "clone"),
        ("write", "write", "write"),
        ("admin", "admin", "admin"),
    ]:
        for owner_sub, expected in [("alice", owner_expected), ("bob", colleague_expected)]:
            seen = {}

            def answer(query, params, _owner=owner_sub, _role=project_role, _seen=seen):
                _seen.update(params)
                return [_conversation_row(owner_sub=_owner, project_role=_role)]

            access = await resolve_access(
                _StubPool(answer), run_id="run-abc", subject="alice", groups=["consultant"]
            )
            resolved = access["role"] if access is not None else None
            assert resolved == expected, (
                f"owner_sub={owner_sub!r} with project role {project_role!r} "
                f"resolved {resolved!r}, expected {expected!r}"
            )
            # The check is anchored on the CALLER's identity, not on anything
            # the client asserted: subject and groups are what the lateral
            # grant lookup matches on, so both must reach the query.
            assert seen["run_id"] == "run-abc", seen
            assert seen["subject"] == "alice", seen
            assert seen["groups"] == ["consultant"], seen


# --------------------------------------------------------------------------
# ADR-0527 criterion 10's security-negative for the rewritten listing.
#
# The listing moved from a single owner_sub predicate to a two-block
# membership join, so the fixture below is a three-table one (conversations
# x projects x project_grants) covering all five shapes ADR-0527's Security
# considerations enumerate. It answers the query list_conversations actually
# built - every join condition AND the final WHERE clause are pulled back
# out of the emitted SQL and evaluated against the fixture - rather than
# reimplementing ADR-0527's visibility rule, which is the failure mode this
# whole exercise exists to remove.
# --------------------------------------------------------------------------


class _SqlNull:
    """SQL NULL, deliberately not Python None: `NULL = NULL` is false in
    Postgres while `None == None` is true in Python, and that difference IS
    the archived-project rule. The projects LEFT JOIN leaves p.project_id
    NULL for an archived project, so the LATERAL's `g.project_id =
    p.project_id` matches nothing and an otherwise live grant row stops
    counting. A fixture that used None would quietly join the archived
    project's grants back on and hide the very leak shape 5 exists to
    catch."""

    def __eq__(self, other):
        return False

    def __ne__(self, other):
        return True

    def __hash__(self):
        return hash(None)

    def __repr__(self):
        return "NULL"


_NULL = _SqlNull()


def _py(value):
    """SQL NULL back to the None psycopg would hand app/conversations.py."""
    return None if isinstance(value, _SqlNull) else value


def _merge(*rows) -> dict:
    merged: dict = {}
    for row in rows:
        merged.update(row)
    return merged


# Only the constructs ADR-0527's listing query uses. Anything else is
# rejected below rather than quietly evaluated, so this helper can never
# decay into the thing it replaces: an assertion that passes whatever the
# code happens to do.
_SQL_TO_PYTHON = [
    (r"%\((\w+)\)s", r'P["\1"]'),
    (r"\b([cpgs])\.(\w+)\b", r'R["\1.\2"]'),
    # The group-membership test consumes its own `=` before the generic
    # operator rule at the bottom would turn it into `==`.
    (r'(R\["[cpgs]\.\w+"\])\s*=\s*ANY\(P\["(\w+)"\]::text\[\]\)', r'\1 in P["\2"]'),
    (r"\bIS NOT NULL\b", "is not null"),
    (r"\bIS NULL\b", "is null"),
    (r"\bAND\b", "and"),
    (r"\bOR\b", "or"),
    (r"(?<![<>!=])=(?!=)", "=="),
]


def _sql_predicate_holds(clause: str, row: dict, params: dict) -> bool:
    expression = " ".join(clause.split())  # one line: the clause is indented SQL
    for pattern, replacement in _SQL_TO_PYTHON:
        expression = re.sub(pattern, replacement, expression)
    unsupported = re.findall(r"[A-Z]{2,}|::", expression)
    assert not unsupported, f"unsupported SQL {unsupported} in the listing clause: {clause!r}"
    return bool(eval(expression, {"__builtins__": {}}, {"R": row, "P": params, "null": _NULL}))  # noqa: S307


def _clause(query: str, after: str, before: str, keyword: str) -> str:
    """One fragment of the emitted listing query: whatever follows `keyword`
    in the section between `after` and `before`. Asserts rather than guesses
    if the query no longer has that shape, so a later rewrite of
    list_conversations can never leave this fixture silently answering from
    a join condition that is no longer in the SQL."""
    assert after in query and before in query, f"{after!r}/{before!r} not in the listing query"
    section = query.split(after, 1)[1].split(before, 1)[0]
    assert keyword in section, f"{keyword!r} not in {section!r}"
    return section.split(keyword, 1)[1]


_UPDATED_AT = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)

_FIXTURE_PROJECTS = [
    {"p.project_id": "proj-shared", "p.archived_at": _NULL},
    {"p.project_id": "proj-other", "p.archived_at": _NULL},
    {"p.project_id": "proj-archived", "p.archived_at": _UPDATED_AT},
]

_NO_PROJECT = {"p.project_id": _NULL, "p.archived_at": _NULL}

# The five shapes, in ADR-0527's own order. Every row is a live (not
# archived) conversation of the same agent, so the only thing deciding
# visibility is the rule under test.
_FIXTURE_CONVERSATIONS = [
    # 1. a private conversation - alice's own, in no project at all.
    {"c.run_id": "run-alice-private", "c.owner_sub": "alice", "c.project_id": _NULL,
     "c.title": "My own notes", "c.agent_name": "tekos", "c.archived_at": _NULL},
    # 2. a project conversation - alice's own, inside a project. It reaches
    #    her through the membership block, not the ownership block: the
    #    first block is deliberately `project_id IS NULL` only, so a
    #    conversation filed in a project is governed by that project.
    {"c.run_id": "run-alice-in-project", "c.owner_sub": "alice", "c.project_id": "proj-shared",
     "c.title": "Migration kickoff", "c.agent_name": "tekos", "c.archived_at": _NULL},
    # 3. a colleague's conversation in a SHARED project - the whole point of
    #    the widening, and the row that must appear only once a grant does.
    {"c.run_id": "run-bob-shared", "c.owner_sub": "bob", "c.project_id": "proj-shared",
     "c.title": "Bob's migration plan", "c.agent_name": "tekos", "c.archived_at": _NULL},
    # 4. a colleague's conversation in an UNSHARED project - alice holds no
    #    grant on proj-other in any direction of this test, so it must never
    #    appear, not even while she is a member of another project.
    {"c.run_id": "run-bob-unshared", "c.owner_sub": "bob", "c.project_id": "proj-other",
     "c.title": "Someone else's account", "c.agent_name": "tekos", "c.archived_at": _NULL},
    # 5. a conversation in an ARCHIVED project - hidden even though the
    #    grant row below is perfectly live. ADR-0527 clause 7's revocation
    #    happens at the project level (archive_project_cascade bumps
    #    grants_revision and pushes an empty member set), and this is the
    #    listing-level guard that the archive is honoured here too.
    {"c.run_id": "run-bob-archived", "c.owner_sub": "bob", "c.project_id": "proj-archived",
     "c.title": "Last year's engagement", "c.agent_name": "tekos", "c.archived_at": _NULL},
]

# Present in BOTH directions on purpose: shape 5 stays hidden because the
# project is archived, never because the grant went away.
_ARCHIVED_PROJECT_GRANT = {"g.project_id": "proj-archived", "g.subject": "alice",
                           "g.group_name": _NULL, "g.role": "write"}


class _FakeConversationsDatabase:
    """Stands in for agent-conversations for the listing query alone. For
    every fixture conversation it replays the query's own join conditions -
    the projects ON clause, then the LATERAL's grant lookup - and finally
    the query's own visibility WHERE clause. Change the rule in
    app/conversations.py and this fixture's answer changes with it, which is
    the point of driving it off the emitted SQL rather than off a copy."""

    def __init__(self, grants):
        self._grants = grants

    def __call__(self, query, params):
        projects_on = _clause(query, "LEFT JOIN projects p", "LEFT JOIN LATERAL", "ON ")
        grants_where = _clause(query, "FROM project_grants g", "ORDER BY", "WHERE ")
        visibility = query.rsplit("WHERE", 1)[1].split("ORDER BY")[0]

        rows = []
        for conversation in _FIXTURE_CONVERSATIONS:
            project = next(
                (p for p in _FIXTURE_PROJECTS
                 if _sql_predicate_holds(projects_on, _merge(conversation, p), params)),
                _NO_PROJECT,  # LEFT JOIN: no match leaves every p.* column NULL
            )
            joined = _merge(conversation, project)
            matching = [g for g in self._grants
                        if _sql_predicate_holds(grants_where, _merge(joined, g), params)]
            # ORDER BY <role rank> DESC LIMIT 1. The SQL rank is
            # _ROLE_RANK_SQL, whose Python twin the module exports as rank_of.
            joined["g.role"] = max(
                (g["g.role"] for g in matching), key=conversations_module.rank_of, default=_NULL
            )
            joined["s.run_id"] = _NULL  # nothing starred in this fixture
            if _sql_predicate_holds(visibility, joined, params):
                rows.append({
                    "run_id": _py(joined["c.run_id"]),
                    "title": _py(joined["c.title"]),
                    "updated_at": _UPDATED_AT,
                    "project_id": _py(joined["c.project_id"]),
                    "starred": joined["s.run_id"] is not _NULL,
                    "owned": joined["c.owner_sub"] == params["subject"],
                    "project_role": _py(joined["g.role"]),
                })
        return rows


async def test_list_conversations_covers_every_shape_adr_0527_enumerates() -> None:
    """ADR-0527 criterion 10's security-negative for the rewritten listing,
    in both directions and across all five shapes its Security
    considerations enumerate. ADR-0212 filtered on owner_sub alone; ADR-0527
    widened that to the two-block membership join, and the entire risk of
    the widening is that it hands a colleague's conversation to someone
    holding no grant on its project.

    Direction 1 - alice holds no grant on the shared project, so neither
    bob's conversation (3) nor her own conversation filed inside that
    project (2) may appear, WHILE her project-less one (1) still does: a
    listing that returned nothing at all would sail through a
    negative-only assertion while being just as broken (see the
    negative-only gate that hid a broken tool in WP-074).

    Direction 2 - the identical call once a grant exists: (2) and (3)
    appear, the colleague's row carrying the granted role so the frontend
    renders it read-only while her own stays writable. Asserted for both
    ways a grant can be held, directly on the subject and through a group,
    which is also what proves the caller's groups reach the query.

    Shapes 4 and 5 are invariants across both directions: the colleague's
    conversation in an unshared project never appears, and neither does the
    one in an archived project - the latter WITH a live grant row in the
    fixture the whole time, because ADR-0527 clause 7's revocation is the
    archive itself, and a listing that honoured only the grant table would
    keep serving an archived engagement to every former member."""
    always_hidden = {"run-bob-unshared", "run-bob-archived"}

    ungranted = await list_conversations(
        _StubPool(_FakeConversationsDatabase([_ARCHIVED_PROJECT_GRANT])),
        agent_name="tekos", subject="alice", groups=["consultant"],
    )
    assert [r["run_id"] for r in ungranted] == ["run-alice-private"], ungranted

    for grant, groups in [
        ({"g.project_id": "proj-shared", "g.subject": "alice", "g.group_name": _NULL, "g.role": "read"},
         ["consultant"]),
        ({"g.project_id": "proj-shared", "g.subject": _NULL, "g.group_name": "sales", "g.role": "read"},
         ["consultant", "sales"]),
    ]:
        granted = await list_conversations(
            _StubPool(_FakeConversationsDatabase([grant, _ARCHIVED_PROJECT_GRANT])),
            agent_name="tekos", subject="alice", groups=groups,
        )
        by_run = {r["run_id"]: r for r in granted}
        assert set(by_run) == {"run-alice-private", "run-alice-in-project", "run-bob-shared"}, granted
        assert not (always_hidden & set(by_run)), granted
        assert by_run["run-bob-shared"]["role"] == "read", by_run["run-bob-shared"]
        assert by_run["run-bob-shared"]["project_id"] == "proj-shared", by_run["run-bob-shared"]
        # Ownership still wins on her own rows (resolve_access's rule applied
        # to the list, so the sidebar and the conversation itself agree),
        # inside a project as well as outside one.
        assert by_run["run-alice-in-project"]["role"] == "write", by_run["run-alice-in-project"]
        assert by_run["run-alice-private"]["role"] == "write", by_run["run-alice-private"]


async def test_role_ranks_form_a_total_order() -> None:
    """ADR-0527 clause 2: read < clone < write < admin, so "the strongest
    grant that matches the caller wins" is well-defined when a direct
    grant and a group grant disagree. rank_of returns 0 - the fail-closed
    floor - for no role at all."""
    assert conversations_module.rank_of(None) == 0
    assert conversations_module.rank_of("nonsense") == 0
    ranks = [conversations_module.rank_of(r) for r in ("read", "clone", "write", "admin")]
    assert ranks == sorted(ranks) and len(set(ranks)) == 4, ranks


async def test_derive_clone_title_increments_rather_than_nesting() -> None:
    """ADR-0527 clause 4: a clone stays in its source project, so it needs
    a name that distinguishes it in the same list without growing a
    "(copy) (copy) (copy)" tail."""
    assert _derive_clone_title("Foo") == "Foo (copy)"
    assert _derive_clone_title("Foo (copy)") == "Foo (copy 2)"
    assert _derive_clone_title("Foo (copy 7)") == "Foo (copy 8)"
    assert _derive_clone_title("") == "Untitled conversation (copy)"


async def test_derive_clone_title_respects_the_rename_ceiling() -> None:
    """Cloning a maximal title must not produce a row the rename endpoint
    (max_length=200 in app/schemas.py) would then refuse."""
    assert len(_derive_clone_title("A" * 250)) <= 200


async def test_clone_conversation_fails_closed_on_a_none_pool() -> None:
    await _expect_503(clone_conversation(None, source_run_id="run-abc", new_run_id="run-def", owner_sub="bob"))


async def test_acquire_write_lock_trivially_succeeds_on_a_none_pool() -> None:
    """ADR-0213: like record_turn, this is the other deliberate exception
    to the fail-closed rule - without conversation persistence configured
    there is no conversation_memberships row anyone else could hold to
    even contend for this lock, so chat must keep working unconditionally."""
    acquired = await acquire_write_lock(None, run_id="run-abc", holder_sub="alice")
    assert acquired is True


async def test_release_write_lock_silently_no_ops_on_a_none_pool() -> None:
    await release_write_lock(None, run_id="run-abc", holder_sub="alice")  # no exception raised = pass


async def test_record_turn_silently_no_ops_on_a_none_pool() -> None:
    """The one deliberate exception to the fail-closed rule above (see
    conversations.py's own docstring): ordinary chat must keep working
    even when conversation persistence isn't configured."""
    await conversations_module.record_turn(
        None, run_id="run-abc", agent_name="tekos", owner_sub="alice", opening_message="hi"
    )  # no exception raised = pass


class _FakePoolThatTimesOut:
    """Stands in for a configured-but-transiently-unavailable pool: unlike
    the None-pool case above, checkout itself raises - proving record_turn
    degrades the same way, not just when the feature is off entirely."""

    @asynccontextmanager
    async def connection(self):
        raise PoolTimeout("couldn't get a connection after 30.00 sec")
        yield  # pragma: no cover - unreachable, keeps this an async generator


async def test_record_turn_swallows_a_transient_pool_timeout() -> None:
    """2026-08-21 live-cluster incident: a configured conversations pool
    that can't hand out a connection within its checkout window must not
    500 the whole chat reply over a missed metadata row - record_turn is
    incidental bookkeeping on the hot /chat path, not something the caller
    asked for."""
    await conversations_module.record_turn(
        _FakePoolThatTimesOut(), run_id="run-abc", agent_name="arkos", owner_sub="alice", opening_message="hi"
    )  # no exception raised = pass


async def test_resolve_run_id_still_defaults_to_checkpoint_only_check() -> None:
    """ADR-0212 widens _resolve_run_id's ownership check, but only when a
    conversations_pool is actually passed - every existing call site
    (and this test) that omits it keeps ADR-0103's original,
    checkpoint-only behavior unchanged."""
    graph = build_graph(MemorySaver())
    run_id = "run-conv-default"
    config = {"configurable": {"thread_id": run_id}}

    await graph.ainvoke(
        {
            "session_id": "s1",
            "user_sub": "alice",
            "groups": [],
            "bearer_token": "t",
            "message": "hi",
            "retrieved_docs": [],
            "tool_results": {},
            "errors": [],
        },
        config=config,
    )

    payload = ChatRequest(session_id="s1", user_sub="alice", message="continue", run_id=run_id)
    resolved = await _resolve_run_id(graph, payload, _identity("alice"))
    assert resolved == run_id

    try:
        await _resolve_run_id(graph, payload, _identity("mallory"))
        raise AssertionError("expected an HTTPException refusing cross-subject resume")
    except HTTPException as exc:
        assert exc.status_code == 403, exc


TESTS = [
    test_conninfo_is_none_when_unconfigured,
    test_conninfo_includes_sslmode_and_dbname,
    test_pool_context_yields_none_when_unconfigured,
    test_derive_title_uses_the_message_as_is_when_short,
    test_derive_title_collapses_whitespace,
    test_derive_title_truncates_long_messages_with_ellipsis,
    test_resolve_owner_fails_closed_on_a_none_pool,
    test_list_conversations_fails_closed_on_a_none_pool,
    test_rename_conversation_fails_closed_on_a_none_pool,
    test_set_star_fails_closed_on_a_none_pool,
    test_archive_conversation_fails_closed_on_a_none_pool,
    test_reorder_conversations_fails_closed_on_a_none_pool,
    test_hard_delete_conversation_fails_closed_on_a_none_pool,
    test_resolve_access_fails_closed_on_a_none_pool,
    test_owner_always_outranks_a_weaker_project_role,
    test_list_conversations_covers_every_shape_adr_0527_enumerates,
    test_role_ranks_form_a_total_order,
    test_derive_clone_title_increments_rather_than_nesting,
    test_derive_clone_title_respects_the_rename_ceiling,
    test_clone_conversation_fails_closed_on_a_none_pool,
    test_acquire_write_lock_trivially_succeeds_on_a_none_pool,
    test_release_write_lock_silently_no_ops_on_a_none_pool,
    test_record_turn_silently_no_ops_on_a_none_pool,
    test_record_turn_swallows_a_transient_pool_timeout,
    test_resolve_run_id_still_defaults_to_checkpoint_only_check,
]


async def _run_all() -> int:
    failures = 0
    for test in TESTS:
        try:
            await test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    return failures


def main() -> int:
    failures = asyncio.run(_run_all())
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
