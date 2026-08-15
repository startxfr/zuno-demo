"""Client for rag-service's project-memory write endpoint (ADR-0209,
WP-28) - the only path Agent Runtime has to persist extracted memory.
rag-service, not this runtime, holds the knowledge.project database
credential (see components/rag-service/app/project_memory.py's module
docstring for why).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag-service.zuno-data.svc:8080")
RAG_TIMEOUT_SECONDS = float(os.getenv("RAG_TIMEOUT_SECONDS", "15"))


class ProjectMemoryClientError(Exception):
    pass


class ProjectMembershipDeniedError(ProjectMemoryClientError):
    """ADR-0209: raised on a 403 from rag-service - the caller has no
    project_memberships row. Fail closed applies to writes exactly like
    reads: the extraction step must not silently drop the denial."""


async def write_project_memory(
    project_id: str,
    caller_sub: str,
    caller_groups: List[str],
    agent: str,
    session_id: Optional[str],
    classification: str,
    facts: List[Dict[str, Any]],
    memories: List[Dict[str, Any]],
) -> Dict[str, int]:
    body: Dict[str, Any] = {
        "project_id": project_id,
        "caller_sub": caller_sub,
        "caller_groups": caller_groups,
        "agent": agent,
        "session_id": session_id,
        "classification": classification,
        "facts": facts,
        "memories": memories,
    }
    try:
        async with httpx.AsyncClient(timeout=RAG_TIMEOUT_SECONDS) as client:
            resp = await client.post(f"{RAG_SERVICE_URL}/v1/project-memory/write", json=body)
        if resp.status_code == 403:
            detail = resp.json().get("detail", "project membership denied") if resp.content else "project membership denied"
            raise ProjectMembershipDeniedError(detail)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise ProjectMemoryClientError(str(exc)) from exc
    return resp.json()
