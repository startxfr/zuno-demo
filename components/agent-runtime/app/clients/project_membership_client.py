"""ADR-0527 clause 8: pushes the project's grant set into rag-service's
`project_memberships` table, which stays the fail-closed gate on
`knowledge.project` retrieval that ADR-0209 made it.

That table is demoted from ACL-of-record to a read-model projection of
`project_grants`. rag-service's own check (app/search.py's
_check_project_membership) is unchanged, so the defence-in-depth property
its docstring is built on survives: rag-service still decides for itself,
against its own database, and never trusts a membership claim from its
caller.

The push goes through rag-service rather than through a second database
credential for the same reason app/clients/project_memory_client.py exists:
rag-service, not this runtime, holds the knowledge.project credential.

Ordering is the whole design (see projects.save_project). The push happens
INSIDE the grant-mutation transaction and before its commit, so a failed
push rolls the mutation back rather than half-applying a revocation. The
monotone `revision` makes the endpoint idempotent and non-rewindable, so a
retry that arrives out of order is ignored rather than resurrecting a
stale grant set.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("agent_runtime.project_membership")

RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag-service.zuno-data.svc:8080")
RAG_TIMEOUT_SECONDS = float(os.getenv("RAG_TIMEOUT_SECONDS", "15"))


class ProjectMembershipSyncError(Exception):
    """Raised on any failure to push. projects.save_project turns this into
    a 503 and rolls back - never into a warning, because a silently
    unsynced revocation leaves rag-project more permissive than the
    authority."""


async def replace_memberships(
    project_id: str,
    revision: int,
    members: List[Dict[str, Optional[str]]],
) -> Dict[str, Any]:
    """Replace-all for one project. `members` carries one
    {"subject": ...} or {"group_name": ...} entry per grant - the role is
    deliberately NOT sent: ADR-0209's membership check is binary, and
    projecting a role rag-service has no use for would invite it to start
    making authorization decisions this ADR keeps in agent-runtime.

    Returns rag-service's response, whose `applied` is False when the
    stored revision is newer (an out-of-order retry) - a success, not an
    error.
    """
    body = {"revision": revision, "members": members}
    url = f"{RAG_SERVICE_URL}/v1/projects/{project_id}/memberships"
    try:
        async with httpx.AsyncClient(timeout=RAG_TIMEOUT_SECONDS) as client:
            resp = await client.put(url, json=body)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise ProjectMembershipSyncError(
            f"could not sync project '{project_id}' membership to rag-service: {exc}"
        ) from exc
    return resp.json()
