"""ADR-0527: the project - the platform's sharing and context boundary.

Three unrelated notions of "project" preceded this module: ADR-0209's
mandatory `project_id` metadata key on `knowledge.project`, guarded by a
binary `project_memberships` table with no API to populate it; ADR-0213's
conversation-level sharing; and ADR-0512's Salesforce opportunity id
doubling as the project's identity. This module is the single object that
replaces all three. It owns project CRUD, grant resolution, and the
projection that keeps rag-service's fail-closed membership gate fed.

Same conventions as app/conversations.py, which shares its pool and its
database: every function here fails closed (503) on a None pool via
`_require_pool`, and no function ever infers a default role. Unlike that
module there is no `record_turn`-style exception - nothing here sits on the
hot chat path, so nothing here has a reason to degrade rather than deny.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Sequence

from fastapi import HTTPException
from psycopg_pool import AsyncConnectionPool

from app.clients import project_membership_client
from app.conversations import ROLE_RANK, _ROLE_RANK_SQL, _require_pool, rank_of

logger = logging.getLogger("agent_runtime.projects")

# ADR-0527 clause 5: the storage and input ceiling for a project's standing
# context. Mirrored in app/schemas.py (request validation), in _DDL's
# ck_projects_context_length (the backstop), and in
# web/src/shared/projects.ts (the live counter). A value that passes the
# first two but not the third is a UI bug; one that passes the first but
# not the second is a schema bug - hence all three.
PROJECT_CONTEXT_MAX_CHARS = 54000

# ADR-0040 keeps two group dimensions apart: agent_<name> entitlement
# ("which agent may this person open at all") and business role ("what may
# they reach inside it"). A project grant is a business-role concept, so an
# entitlement group is never a valid grant target - admitting one would
# turn "shared with the consultants" into "shared with everyone who can
# open Tekos". Enforced on BOTH sides: a grant naming such a group is
# rejected, and a caller's own agent_* groups are stripped before they can
# resolve one, so neither a bad write nor a stale row can widen access.
_ENTITLEMENT_GROUP_PREFIX = "agent_"


def business_role_groups(groups: Sequence[str]) -> List[str]:
    """The caller's business-role groups, normalized. Keycloak emits full
    paths with a leading slash (`/consultant`); app/auth.py already strips
    it, but this function is defensive because it is the only thing
    standing between an entitlement group and a grant match."""
    out: List[str] = []
    for raw in groups or []:
        name = (raw or "").lstrip("/").strip()
        if not name or name.startswith(_ENTITLEMENT_GROUP_PREFIX):
            continue
        out.append(name)
    return out


def _new_project_id() -> str:
    """ADR-0528: never the Salesforce id. This value is emitted in
    X-Zuno-Project-Id and as the zuno.project_id span attribute, so it must
    carry no business meaning."""
    return str(uuid.uuid4())


def assert_grants_are_valid(grants: Sequence[Dict[str, Any]]) -> None:
    """ADR-0527 clause 3's last-admin guard plus the grant-shape rules,
    applied to the full desired set before anything is written. Raising
    here rather than relying on the SQL constraints alone lets the caller
    return a 400 that says which rule failed.

    The last-admin check demands a SUBJECT-scoped admin: a group-scoped one
    would leave the project administrable only for as long as Keycloak
    keeps somebody in that group, which is exactly the kind of remote
    dependency this guard exists to avoid."""
    seen_subjects: set = set()
    seen_groups: set = set()
    has_subject_admin = False

    for grant in grants:
        subject = (grant.get("subject") or "").strip() or None
        group_name = (grant.get("group_name") or "").strip() or None
        role = grant.get("role")

        if (subject is None) == (group_name is None):
            raise HTTPException(
                status_code=400,
                detail="each grant must name exactly one of subject or group_name",
            )
        if role not in ROLE_RANK:
            raise HTTPException(
                status_code=400,
                detail=f"role must be one of {', '.join(ROLE_RANK)}",
            )
        if group_name is not None and group_name.startswith(_ENTITLEMENT_GROUP_PREFIX):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"'{group_name}' is an agent entitlement group (ADR-0040), not a business-role "
                    "group - it cannot be a project grant target"
                ),
            )
        if subject is not None:
            if subject in seen_subjects:
                raise HTTPException(status_code=400, detail=f"duplicate grant for subject '{subject}'")
            seen_subjects.add(subject)
            if role == "admin":
                has_subject_admin = True
        else:
            if group_name in seen_groups:
                raise HTTPException(status_code=400, detail=f"duplicate grant for group '{group_name}'")
            seen_groups.add(group_name)

    if not has_subject_admin:
        raise HTTPException(
            status_code=400,
            detail="a project must keep at least one user with the admin role",
        )


async def effective_role(
    pool: Optional[AsyncConnectionPool], *, project_id: str, subject: str, groups: Sequence[str]
) -> Optional[str]:
    """The caller's strongest grant on a live project, or None - the
    fail-closed denial. Never guesses a default.

    Archived projects resolve to None: a soft-deleted project must behave
    like one that was never shared, or a cascade archive would leave its
    conversations reachable through their own project_id."""
    pool = _require_pool(pool)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"""
                SELECT g.role FROM project_grants g
                JOIN projects p ON p.project_id = g.project_id
                WHERE g.project_id = %(project_id)s
                  AND p.archived_at IS NULL
                  AND (g.subject = %(subject)s OR g.group_name = ANY(%(groups)s::text[]))
                ORDER BY {_ROLE_RANK_SQL} DESC
                LIMIT 1
                """,
                {
                    "project_id": project_id,
                    "subject": subject,
                    "groups": business_role_groups(groups),
                },
            )
            row = await cur.fetchone()
    return row["role"] if row else None


async def require_role(
    pool: Optional[AsyncConnectionPool],
    *,
    project_id: str,
    subject: str,
    groups: Sequence[str],
    minimum: str,
) -> str:
    """effective_role plus the denial. 404 rather than 403 when the caller
    has no role at all, so this surface never confirms that a project they
    cannot see exists; 403 once they demonstrably hold *some* role but not
    a strong enough one, which is information they already have."""
    role = await effective_role(pool, project_id=project_id, subject=subject, groups=groups)
    if role is None:
        raise HTTPException(status_code=404, detail="project not found")
    if rank_of(role) < rank_of(minimum):
        raise HTTPException(
            status_code=403,
            detail=f"this action requires the '{minimum}' role on the project",
        )
    return role


async def list_projects(
    pool: Optional[AsyncConnectionPool], *, subject: str, groups: Sequence[str]
) -> List[Dict[str, Any]]:
    """Every live project the caller holds a grant on, with their effective
    role, their personal star and a live conversation count.

    Deliberately NOT scoped to an agent: ADR-0527 clause 6 makes a project
    cross-agent (the same engagement seen from Tekos and from Arkos is one
    project), while only its conversations are agent-scoped. The count is
    across all agents for the same reason - it describes the project, not
    this sidebar."""
    pool = _require_pool(pool)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"""
                SELECT p.project_id, p.title, p.classification,
                       p.salesforce_opportunity_id IS NOT NULL AS is_customer,
                       p.updated_at,
                       (s.project_id IS NOT NULL) AS starred,
                       g.role,
                       (SELECT count(*) FROM conversations c
                        WHERE c.project_id = p.project_id AND c.archived_at IS NULL) AS conversation_count
                FROM projects p
                LEFT JOIN project_stars s
                       ON s.project_id = p.project_id AND s.subject = %(subject)s
                JOIN LATERAL (
                    SELECT g.role FROM project_grants g
                    WHERE g.project_id = p.project_id
                      AND (g.subject = %(subject)s OR g.group_name = ANY(%(groups)s::text[]))
                    ORDER BY {_ROLE_RANK_SQL} DESC
                    LIMIT 1
                ) g ON TRUE
                WHERE p.archived_at IS NULL
                ORDER BY starred DESC, lower(p.title) ASC
                """,
                {"subject": subject, "groups": business_role_groups(groups)},
            )
            rows = await cur.fetchall()
    return [
        {
            "project_id": r["project_id"],
            "title": r["title"],
            "classification": r["classification"],
            "is_customer": bool(r["is_customer"]),
            "starred": r["starred"],
            "role": r["role"],
            "conversation_count": int(r["conversation_count"]),
            "updated_at": r["updated_at"].isoformat(),
        }
        for r in rows
    ]


async def get_project(
    pool: Optional[AsyncConnectionPool], *, project_id: str, subject: str, groups: Sequence[str]
) -> Dict[str, Any]:
    """The full project. `grants` and `salesforce_opportunity_id` are
    included ONLY for an admin: the grant list names colleagues, and
    ADR-0528 keeps the Salesforce identifier out of every surface that does
    not strictly need it."""
    role = await require_role(pool, project_id=project_id, subject=subject, groups=groups, minimum="read")
    pool = _require_pool(pool)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT project_id, title, context, classification,
                       salesforce_opportunity_id, salesforce_verified_at,
                       created_by, created_at, updated_at
                FROM projects WHERE project_id = %s AND archived_at IS NULL
                """,
                (project_id,),
            )
            row = await cur.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="project not found")

            grants: List[Dict[str, Any]] = []
            if role == "admin":
                await cur.execute(
                    "SELECT subject, group_name, role, granted_by, created_at "
                    "FROM project_grants WHERE project_id = %s "
                    "ORDER BY (subject IS NULL), lower(coalesce(subject, group_name))",
                    (project_id,),
                )
                grants = [
                    {
                        "subject": g["subject"],
                        "group_name": g["group_name"],
                        "role": g["role"],
                        "granted_by": g["granted_by"],
                        "created_at": g["created_at"].isoformat(),
                    }
                    for g in await cur.fetchall()
                ]

    detail: Dict[str, Any] = {
        "project_id": row["project_id"],
        "title": row["title"],
        "context": row["context"],
        "classification": row["classification"],
        "is_customer": row["salesforce_opportunity_id"] is not None,
        "role": role,
        "created_by": row["created_by"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
        "grants": grants,
    }
    if role == "admin":
        detail["salesforce_opportunity_id"] = row["salesforce_opportunity_id"]
        detail["salesforce_verified_at"] = (
            row["salesforce_verified_at"].isoformat() if row["salesforce_verified_at"] else None
        )
    return detail


async def delete_preview(pool: Optional[AsyncConnectionPool], *, project_id: str, subject: str) -> Dict[str, int]:
    """The counts ADR-0527 clause 7 requires the confirmation to name -
    including how many conversations belong to someone else, because a
    project admin archiving colleagues' visible work should be told the
    size of what they are doing."""
    pool = _require_pool(pool)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    count(*) FILTER (WHERE c.archived_at IS NULL) AS conversations_total,
                    count(*) FILTER (WHERE c.archived_at IS NULL AND c.owner_sub <> %(subject)s)
                        AS conversations_other_owners
                FROM conversations c WHERE c.project_id = %(project_id)s
                """,
                {"project_id": project_id, "subject": subject},
            )
            conv = await cur.fetchone()
            await cur.execute(
                """
                SELECT count(*) FILTER (WHERE subject IS NOT NULL) AS members_users,
                       count(*) FILTER (WHERE group_name IS NOT NULL) AS members_groups
                FROM project_grants WHERE project_id = %s
                """,
                (project_id,),
            )
            grants = await cur.fetchone()
    return {
        "conversations_total": int(conv["conversations_total"]),
        "conversations_other_owners": int(conv["conversations_other_owners"]),
        "members_users": int(grants["members_users"]),
        "members_groups": int(grants["members_groups"]),
    }


async def archive_project_cascade(
    pool: Optional[AsyncConnectionPool], *, project_id: str
) -> Dict[str, int]:
    """ADR-0527 clause 7: soft-delete the project and every conversation in
    it, in one transaction, including conversations owned by other members.
    Nothing is erased - the irreversible purge stays per-conversation and
    owner-only - so this is recoverable by an operator clearing
    archived_at, which is why it is offered to a project admin at all."""
    pool = _require_pool(pool)
    async with pool.connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE conversations SET archived_at = now() "
                    "WHERE project_id = %s AND archived_at IS NULL",
                    (project_id,),
                )
                conversations_archived = cur.rowcount
                await cur.execute(
                    "UPDATE projects SET archived_at = now(), updated_at = now(), "
                    "grants_revision = grants_revision + 1 "
                    "WHERE project_id = %s AND archived_at IS NULL "
                    "RETURNING grants_revision",
                    (project_id,),
                )
                row = await cur.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="project not found")
            # Archiving must REVOKE knowledge.project access, not merely hide
            # the project from the sidebar. rag-service authorizes purely on a
            # row existing in project_memberships (search.py's
            # _check_project_membership); it has no notion of archived_at and
            # cannot have one, since it does not own the projects table. So
            # leaving the projection in place leaves an archived project's
            # memory readable to everyone who was a member.
            #
            # Found live on 2026-08-28: three archived projects still carried
            # their membership rows. reconcile_projections already filtered
            # `archived_at IS NULL`, so the intent was always that archived
            # projects are absent from the projection - but nothing removed
            # them, and skipping them at startup meant nothing repaired it.
            #
            # project_grants is left intact on purpose: archiving is
            # recoverable by an operator clearing archived_at, and the
            # projection is rebuilt from those grants by the next
            # reconcile_projections or any later save.
            await revoke_projection(conn, project_id, int(row["grants_revision"]))
    return {"conversations_archived": conversations_archived}


async def revoke_projection(conn, project_id: str, revision: int) -> None:
    """The archive-time counterpart of _push_projection: pushes an EMPTY
    member set, inside the caller's open transaction, with the same
    fail-closed-and-roll-back contract. If rag-service cannot be reached the
    archive is rolled back rather than half-applied - an archive that left
    access behind is the exact failure this exists to prevent."""
    try:
        await project_membership_client.replace_memberships(project_id, revision, [])
    except project_membership_client.ProjectMembershipSyncError as exc:
        logger.error("project membership revocation failed for %s: %s", project_id, exc)
        raise HTTPException(
            status_code=503,
            detail="the project directory is unavailable - no change was applied",
        ) from exc


async def set_project_star(
    pool: Optional[AsyncConnectionPool], *, project_id: str, subject: str, starred: bool
) -> None:
    """A member's private organizing flag over a project they can already
    see - the caller checks the read role first."""
    pool = _require_pool(pool)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            if starred:
                await cur.execute(
                    "INSERT INTO project_stars (project_id, subject) VALUES (%s, %s) "
                    "ON CONFLICT (project_id, subject) DO NOTHING",
                    (project_id, subject),
                )
            else:
                await cur.execute(
                    "DELETE FROM project_stars WHERE project_id = %s AND subject = %s",
                    (project_id, subject),
                )


async def _push_projection(conn, project_id: str, revision: int) -> None:
    """Reads the grant set that is about to be committed and pushes it to
    rag-service, INSIDE the caller's open transaction. Reading through
    `conn` rather than a fresh connection is what makes the push describe
    the state being committed rather than the state before it."""
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT subject, group_name FROM project_grants WHERE project_id = %s",
            (project_id,),
        )
        members = [
            {"subject": r["subject"], "group_name": r["group_name"]}
            for r in await cur.fetchall()
        ]
    try:
        await project_membership_client.replace_memberships(project_id, revision, members)
    except project_membership_client.ProjectMembershipSyncError as exc:
        # Fail closed and roll back: a revocation that reached
        # project_grants but not project_memberships would leave
        # knowledge.project readable by someone who was just removed.
        logger.error("project membership projection failed for %s: %s", project_id, exc)
        raise HTTPException(
            status_code=503,
            detail="the project directory is unavailable - no change was applied",
        ) from exc


async def create_project(
    pool: Optional[AsyncConnectionPool],
    *,
    title: str,
    context: str,
    classification: str,
    salesforce_opportunity_id: Optional[str],
    salesforce_verified_at: Optional[Any],
    created_by: str,
    grants: Sequence[Dict[str, Any]],
) -> str:
    """ADR-0527 clause 3: no owner column - the creator is simply given an
    `admin` grant, which the caller has already merged into `grants`.
    Project row, grants and projection all land in one transaction, so a
    project can never exist with nobody able to administer it."""
    assert_grants_are_valid(grants)
    pool = _require_pool(pool)
    project_id = _new_project_id()
    async with pool.connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO projects (
                        project_id, title, context, classification,
                        salesforce_opportunity_id, salesforce_verified_at, created_by
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        project_id, title, context, classification,
                        salesforce_opportunity_id, salesforce_verified_at, created_by,
                    ),
                )
                await _write_grants(cur, project_id, grants, granted_by=created_by)
            await _push_projection(conn, project_id, revision=1)
    logger.info("project created: %s by %s (%d grant(s))", project_id, created_by, len(grants))
    return project_id


async def save_project(
    pool: Optional[AsyncConnectionPool],
    *,
    project_id: str,
    title: str,
    context: str,
    salesforce_opportunity_id: Optional[str],
    salesforce_verified_at: Optional[Any],
    grants: Optional[Sequence[Dict[str, Any]]],
    actor: str,
) -> None:
    """The single-save commit behind ADR-0527 clause 9's dialog: the whole
    desired state arrives at once and replaces what is stored, which is why
    this ADR needs one endpoint where ADR-0213 needed five.

    `grants=None` means "the caller may not edit grants" (a `write` member
    editing the Description tab) and leaves them untouched. A non-None
    value is the FULL desired set - anything absent from it is revoked.

    Ordering, which is the point: bump the revision, apply the grants, push
    the projection, and only then let the transaction commit. A push
    failure raises before the commit, so the mutation is a no-op rather
    than a half-applied revocation."""
    if grants is not None:
        assert_grants_are_valid(grants)
    pool = _require_pool(pool)
    async with pool.connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE projects SET
                        title = %(title)s,
                        context = %(context)s,
                        salesforce_opportunity_id = %(sf_id)s,
                        salesforce_verified_at = %(sf_at)s,
                        grants_revision = grants_revision + 1,
                        updated_at = now()
                    WHERE project_id = %(project_id)s AND archived_at IS NULL
                    RETURNING grants_revision
                    """,
                    {
                        "title": title,
                        "context": context,
                        "sf_id": salesforce_opportunity_id,
                        "sf_at": salesforce_verified_at,
                        "project_id": project_id,
                    },
                )
                row = await cur.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="project not found")
                revision = int(row["grants_revision"])

                if grants is not None:
                    await cur.execute("DELETE FROM project_grants WHERE project_id = %s", (project_id,))
                    await _write_grants(cur, project_id, grants, granted_by=actor)

            await _push_projection(conn, project_id, revision)
    logger.info("project saved: %s by %s (revision %d)", project_id, actor, revision)


async def _write_grants(
    cur, project_id: str, grants: Sequence[Dict[str, Any]], *, granted_by: str
) -> None:
    """Insert the desired grant set. Callers have already run
    assert_grants_are_valid, so the SQL constraints here are a backstop,
    not the validation."""
    for grant in grants:
        subject = (grant.get("subject") or "").strip() or None
        group_name = (grant.get("group_name") or "").strip() or None
        await cur.execute(
            "INSERT INTO project_grants (project_id, subject, group_name, role, granted_by) "
            "VALUES (%s, %s, %s, %s, %s)",
            (project_id, subject, group_name, grant["role"], granted_by),
        )


async def reconcile_projections(pool: Optional[AsyncConnectionPool]) -> int:
    """Best-effort re-push of every live project's grant set at startup,
    repairing any divergence left by the residual window in save_project
    (push succeeded, commit then failed) or by a rag-service outage that
    outlasted a retry.

    Deliberately non-fatal and logged rather than raised: a rag-service
    outage must not stop agent-runtime from booting, and the projection is
    a *deny* gate - a stale one denies too much, never too little, for
    every case except a revocation that never landed, which this call is
    what fixes."""
    if pool is None:
        return 0
    pushed = 0
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # Archived projects are included on purpose and push an
                # empty member set below: skipping them (as this did until
                # 2026-08-28) means a projection left behind by an archive
                # predating the revocation fix is never repaired.
                await cur.execute(
                    "SELECT project_id, grants_revision, archived_at IS NOT NULL AS archived "
                    "FROM projects"
                )
                projects = await cur.fetchall()
            for row in projects:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT subject, group_name FROM project_grants WHERE project_id = %s",
                        (row["project_id"],),
                    )
                    members = (
                        []
                        if row["archived"]
                        else [
                            {"subject": r["subject"], "group_name": r["group_name"]}
                            for r in await cur.fetchall()
                        ]
                    )
                await project_membership_client.replace_memberships(
                    row["project_id"], int(row["grants_revision"]), members
                )
                pushed += 1
    except Exception as exc:  # noqa: BLE001 - startup must never fail on this
        logger.warning(
            "project membership reconciliation incomplete after %d project(s): %s", pushed, exc
        )
        return pushed
    if pushed:
        logger.info("reconciled project membership projection for %d project(s)", pushed)
    return pushed


async def stamp_salesforce_verification(
    pool: Optional[AsyncConnectionPool], *, project_id: str
) -> None:
    """ADR-0528: refresh salesforce_verified_at after a successful
    re-verification, so the next turn inside this project's validity
    window makes no Salesforce call at all. Only ever called once
    project_binding.verify_project_binding has already succeeded - this
    function never decides that anything is verified, it only records that
    something was."""
    pool = _require_pool(pool)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE projects SET salesforce_verified_at = now(), updated_at = now() "
                "WHERE project_id = %s AND salesforce_opportunity_id IS NOT NULL",
                (project_id,),
            )
