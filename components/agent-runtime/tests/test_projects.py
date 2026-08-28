"""ADR-0527 (WP-088): the project entity, its four-role RBAC and the
membership projection.

Same convention as every other suite in this directory: a standalone
script with a TESTS list, no pytest, no live Postgres. What is provable
without a database is proved here - the pure guards (last-admin,
entitlement groups, grant shape), the fail-closed posture of every new
persistence function, and the rollback ordering that keeps a revocation
from being half-applied. The SQL itself (resolve_access's lateral join,
list_conversations' four-disjunct predicate) is exercised against the real
agent-conversations database on the cluster, per this component's README.
"""
import asyncio
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))

from fastapi import HTTPException  # noqa: E402

import app.projects as projects  # noqa: E402
from app.conversations import ROLE_RANK  # noqa: E402


async def _expect_503(awaitable) -> None:
    try:
        await awaitable
    except HTTPException as exc:
        assert exc.status_code == 503, f"expected 503, got {exc.status_code}"
        return
    raise AssertionError("expected an HTTPException(503), nothing was raised")


def _expect_400(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except HTTPException as exc:
        assert exc.status_code == 400, f"expected 400, got {exc.status_code}"
        return str(exc.detail)
    raise AssertionError("expected an HTTPException(400), nothing was raised")


# --------------------------------------------------------------------------
# ADR-0527 clause 2: business-role groups only
# --------------------------------------------------------------------------


async def test_entitlement_groups_never_resolve_a_grant() -> None:
    """ADR-0040 keeps agent_<name> entitlement ("which agent may I open")
    apart from business role ("what may I reach inside it"). Letting an
    entitlement group resolve a project grant would collapse the two -
    "shared with the consultants" would become "shared with everyone who
    can open Tekos"."""
    assert projects.business_role_groups(["/consultant", "/agent_tekos"]) == ["consultant"]
    assert projects.business_role_groups(["agent_arkos", "agent_finage"]) == []
    assert projects.business_role_groups([]) == []
    # Leading slashes are stripped defensively even though app/auth.py
    # already does it - this function is the last thing standing between
    # an entitlement group and a grant match.
    assert projects.business_role_groups(["/sales", "board"]) == ["sales", "board"]


async def test_entitlement_groups_are_refused_as_grant_targets() -> None:
    """The same rule on the write side. Enforced on BOTH sides so neither a
    bad write nor a stale row can widen access."""
    detail = _expect_400(
        projects.assert_grants_are_valid,
        [
            {"subject": "alice", "group_name": None, "role": "admin"},
            {"subject": None, "group_name": "agent_tekos", "role": "read"},
        ],
    )
    assert "entitlement group" in detail, detail


# --------------------------------------------------------------------------
# ADR-0527 clause 3: the last-admin guard
# --------------------------------------------------------------------------


async def test_a_grant_set_with_no_admin_is_refused() -> None:
    """Replaces the single-owner column: a project must never become
    unadministrable. Covers revocation (nobody left) and demotion (the
    last admin downgraded) alike, since both arrive as the same full
    desired set."""
    _expect_400(projects.assert_grants_are_valid, [])
    _expect_400(projects.assert_grants_are_valid, [{"subject": "alice", "group_name": None, "role": "write"}])


async def test_a_group_admin_alone_does_not_satisfy_the_guard() -> None:
    """The guard demands a SUBJECT-scoped admin. A group-scoped one leaves
    the project administrable only for as long as Keycloak keeps somebody
    in that group - a remote dependency this guard exists to avoid."""
    _expect_400(
        projects.assert_grants_are_valid,
        [{"subject": None, "group_name": "consultant", "role": "admin"}],
    )
    # ... but a subject admin alongside a group admin is fine.
    projects.assert_grants_are_valid(
        [
            {"subject": "alice", "group_name": None, "role": "admin"},
            {"subject": None, "group_name": "consultant", "role": "admin"},
        ]
    )


async def test_grant_shape_and_duplicate_rules() -> None:
    """XOR, not ADR-0209's inclusive OR: the RBAC tab renders one row per
    grant under either a Users or a Groups subsection, and a row carrying
    both would have no unambiguous home nor revoke semantics."""
    admin = {"subject": "alice", "group_name": None, "role": "admin"}
    _expect_400(projects.assert_grants_are_valid, [admin, {"subject": "bob", "group_name": "sales", "role": "read"}])
    _expect_400(projects.assert_grants_are_valid, [admin, {"subject": None, "group_name": None, "role": "read"}])
    _expect_400(projects.assert_grants_are_valid, [admin, {"subject": "bob", "group_name": None, "role": "owner"}])
    _expect_400(projects.assert_grants_are_valid, [admin, {"subject": "alice", "group_name": None, "role": "read"}])
    _expect_400(
        projects.assert_grants_are_valid,
        [admin, {"subject": None, "group_name": "sales", "role": "read"},
         {"subject": None, "group_name": "sales", "role": "write"}],
    )


async def test_every_valid_role_is_accepted() -> None:
    for role in ROLE_RANK:
        projects.assert_grants_are_valid(
            [{"subject": "alice", "group_name": None, "role": "admin"},
             {"subject": "bob", "group_name": None, "role": role}]
        )


# --------------------------------------------------------------------------
# Fail-closed posture (ADR-0527 Security considerations)
# --------------------------------------------------------------------------


async def test_every_persistence_function_fails_closed_on_a_none_pool() -> None:
    """Unlike app/conversations.py, this module has NO record_turn-style
    exception: nothing here sits on the hot chat path, so nothing here has
    a reason to degrade rather than deny."""
    await _expect_503(projects.list_projects(None, subject="alice", groups=[]))
    await _expect_503(projects.effective_role(None, project_id="p", subject="alice", groups=[]))
    await _expect_503(projects.require_role(None, project_id="p", subject="alice", groups=[], minimum="read"))
    await _expect_503(projects.get_project(None, project_id="p", subject="alice", groups=[]))
    await _expect_503(projects.delete_preview(None, project_id="p", subject="alice"))
    await _expect_503(projects.archive_project_cascade(None, project_id="p"))
    await _expect_503(projects.set_project_star(None, project_id="p", subject="alice", starred=True))
    await _expect_503(projects.stamp_salesforce_verification(None, project_id="p"))
    await _expect_503(
        projects.create_project(
            None, title="T", context="", classification="C2", salesforce_opportunity_id=None,
            salesforce_verified_at=None, created_by="alice",
            grants=[{"subject": "alice", "group_name": None, "role": "admin"}],
        )
    )
    await _expect_503(
        projects.save_project(
            None, project_id="p", title="T", context="", salesforce_opportunity_id=None,
            salesforce_verified_at=None,
            grants=[{"subject": "alice", "group_name": None, "role": "admin"}], actor="alice",
        )
    )


async def test_reconcile_projections_never_fails_startup() -> None:
    """ADR-0527 clause 8's one deliberate non-fail-closed path: a
    rag-service outage must not stop agent-runtime from booting, and the
    projection is a DENY gate - a stale one over-denies, the safe
    direction. Returns 0 rather than raising."""
    assert await projects.reconcile_projections(None) == 0


async def test_require_role_hides_projects_the_caller_cannot_see() -> None:
    """404 (not 403) when the caller holds no grant at all, so this
    surface never confirms that a project they cannot see exists. 403 only
    once they demonstrably hold SOME role - information they already
    have."""
    saved = projects.effective_role

    async def no_role(pool, *, project_id, subject, groups):
        return None

    async def weak_role(pool, *, project_id, subject, groups):
        return "read"

    try:
        projects.effective_role = no_role
        try:
            await projects.require_role(object(), project_id="p", subject="a", groups=[], minimum="read")
            raise AssertionError("expected HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 404, exc.status_code

        projects.effective_role = weak_role
        try:
            await projects.require_role(object(), project_id="p", subject="a", groups=[], minimum="admin")
            raise AssertionError("expected HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 403, exc.status_code
        # ...and a sufficient role simply returns it.
        assert await projects.require_role(object(), project_id="p", subject="a", groups=[], minimum="read") == "read"
    finally:
        projects.effective_role = saved


# --------------------------------------------------------------------------
# ADR-0527 clause 8: the projection push is what makes a revocation atomic
# --------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, *a, **kw):
        return None

    async def fetchall(self):
        return self._rows

    async def fetchone(self):
        return {"grants_revision": 7}


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _FakeCursor(self._rows)

    def transaction(self):
        return _FakeTransaction()


async def test_a_failed_projection_push_raises_503_before_any_commit() -> None:
    """The ordering IS the design: the push happens inside the open
    transaction and before its commit, so a rag-service failure makes the
    whole grant mutation a no-op rather than a half-applied revocation
    that leaves knowledge.project readable by someone just removed."""
    from app.clients import project_membership_client

    saved = project_membership_client.replace_memberships

    async def failing_replace(project_id, revision, members):
        raise project_membership_client.ProjectMembershipSyncError("rag-service down")

    project_membership_client.replace_memberships = failing_replace
    try:
        conn = _FakeConn([{"subject": "alice", "group_name": None}])
        try:
            await projects._push_projection(conn, "proj-1", revision=7)
            raise AssertionError("expected HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 503, exc.status_code
            assert "no change was applied" in str(exc.detail), exc.detail
    finally:
        project_membership_client.replace_memberships = saved


async def test_the_projection_carries_targets_but_never_roles() -> None:
    """ADR-0209's membership check is binary. Projecting a role rag-service
    has no use for would invite it to start making authorization decisions
    ADR-0527 keeps in agent-runtime."""
    from app.clients import project_membership_client

    seen = {}
    saved = project_membership_client.replace_memberships

    async def capture(project_id, revision, members):
        seen["project_id"] = project_id
        seen["revision"] = revision
        seen["members"] = members
        return {"applied": True, "revision": revision, "rows": len(members)}

    project_membership_client.replace_memberships = capture
    try:
        conn = _FakeConn([{"subject": "alice", "group_name": None}, {"subject": None, "group_name": "sales"}])
        await projects._push_projection(conn, "proj-1", revision=7)
    finally:
        project_membership_client.replace_memberships = saved

    assert seen["project_id"] == "proj-1" and seen["revision"] == 7
    assert seen["members"] == [
        {"subject": "alice", "group_name": None},
        {"subject": None, "group_name": "sales"},
    ], seen["members"]
    assert all("role" not in m for m in seen["members"])


async def test_context_ceiling_matches_the_schema_and_the_ddl() -> None:
    """ADR-0527 clause 5: 54000 is stated in three places on purpose (the
    request schema, the SQL CHECK, the browser counter). A value that
    passes one but not another is a bug in whichever drifted, so pin the
    two that live in Python together."""
    from app.schemas import PROJECT_CONTEXT_MAX_CHARS as schema_max

    assert projects.PROJECT_CONTEXT_MAX_CHARS == 54000
    assert schema_max == projects.PROJECT_CONTEXT_MAX_CHARS

    ddl = pathlib.Path(__file__).resolve().parents[1] / "app" / "conversations.py"
    assert "char_length(context) <= 54000" in ddl.read_text(), (
        "the projects DDL's ck_projects_context_length no longer matches PROJECT_CONTEXT_MAX_CHARS"
    )


async def test_archiving_revokes_the_projection_rather_than_only_hiding() -> None:
    """ADR-0527 clause 7. rag-service authorizes knowledge.project purely on
    a project_memberships row existing - search.py's _check_project_membership
    has no notion of archived_at and cannot have one, since it does not own
    the projects table. So an archive that leaves the projection in place
    leaves the archived project's memory readable to every former member.

    Found live on 2026-08-28: three archived projects still had their
    membership rows, and reconcile_projections skipped them rather than
    clearing them, so nothing ever repaired it.
    """
    from app.clients import project_membership_client

    seen = {}
    saved = project_membership_client.replace_memberships

    async def capture(project_id, revision, members):
        seen["project_id"] = project_id
        seen["revision"] = revision
        seen["members"] = members
        return {"applied": True, "revision": revision, "rows": len(members)}

    project_membership_client.replace_memberships = capture
    try:
        await projects.revoke_projection(None, "proj-9", 12)
    finally:
        project_membership_client.replace_memberships = saved

    assert seen["project_id"] == "proj-9"
    assert seen["revision"] == 12
    assert seen["members"] == [], (
        "archiving must push an EMPTY member set - anything else leaves access behind"
    )


async def test_a_failed_revocation_rolls_the_archive_back() -> None:
    """Same fail-closed contract _push_projection has, for the same reason
    in reverse: an archive that reached `projects` but not
    `project_memberships` is precisely the half-applied state that leaves
    knowledge.project readable after the project is gone."""
    from app.clients import project_membership_client

    saved = project_membership_client.replace_memberships

    async def failing(project_id, revision, members):
        raise project_membership_client.ProjectMembershipSyncError("rag-service down")

    project_membership_client.replace_memberships = failing
    try:
        await _expect_503(
            projects.revoke_projection(None, "proj-9", 12)
        )
    finally:
        project_membership_client.replace_memberships = saved


TESTS = [
    test_entitlement_groups_never_resolve_a_grant,
    test_entitlement_groups_are_refused_as_grant_targets,
    test_a_grant_set_with_no_admin_is_refused,
    test_a_group_admin_alone_does_not_satisfy_the_guard,
    test_grant_shape_and_duplicate_rules,
    test_every_valid_role_is_accepted,
    test_every_persistence_function_fails_closed_on_a_none_pool,
    test_reconcile_projections_never_fails_startup,
    test_require_role_hides_projects_the_caller_cannot_see,
    test_a_failed_projection_push_raises_503_before_any_commit,
    test_the_projection_carries_targets_but_never_roles,
    test_archiving_revokes_the_projection_rather_than_only_hiding,
    test_a_failed_revocation_rolls_the_archive_back,
    test_context_ceiling_matches_the_schema_and_the_ddl,
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
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
