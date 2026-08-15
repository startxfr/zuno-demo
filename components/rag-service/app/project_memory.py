"""ADR-0209 (WP-28): persistence for knowledge.project - the write side
Agent Runtime's memory-extraction step calls into (app/main.py's
POST /v1/project-memory/write). rag-service is the one data-access
boundary for every knowledge domain (WP-21); this keeps that property
true for project memory's writes the same way it's already true for every
domain's reads, rather than giving Agent Runtime its own direct database
credential.

Two persistence concerns, per ADR-0209's Decision:
- structured project state -> project_state rows, upserted by
  (project_id, key) - "OpenShift 4.22" is a lookup, not a similarity
  search.
- semantic project memories -> document_embeddings rows, embedded the
  same way a search query is (app/embeddings.py) so hybrid_search's
  existing vector+text retrieval finds them later with no special-casing.

The fail-closed project_memberships check (app/search.py's
_check_project_membership) runs here too, before any write - the same
membership gate write and read share, since a caller with no read access
to a project has no business writing to it either.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db import get_pool
from app.embeddings import embed_query
from app.search import ProjectMembershipDenied, _check_project_membership

logger = logging.getLogger("rag_service.project_memory")

_PROJECT_DOMAIN = "knowledge.project"


class ProjectMemoryError(RuntimeError):
    pass


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _memory_id_for(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


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
    """Persists one extraction step's output. Raises ProjectMembershipDenied
    (fail closed, ADR-0209) if the caller has no project_memberships row -
    checked once, before either table is touched, so a denial never
    partially writes.
    """
    pool = get_pool(_PROJECT_DOMAIN)
    if pool is None:
        raise ProjectMemoryError(f"no live database pool for domain '{_PROJECT_DOMAIN}'")

    await _check_project_membership(pool, project_id, caller_sub, caller_groups)

    facts_written = 0
    memories_written = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            for fact in facts:
                key = fact["key"]
                value = fact["value"]
                await conn.execute(
                    """
                    INSERT INTO project_state
                        (project_id, key, value, author_sub, agent, session_id, classification, acl_groups)
                    VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7, $8::jsonb)
                    ON CONFLICT (project_id, key) DO UPDATE SET
                        value = EXCLUDED.value,
                        author_sub = EXCLUDED.author_sub,
                        agent = EXCLUDED.agent,
                        session_id = EXCLUDED.session_id,
                        classification = EXCLUDED.classification,
                        acl_groups = EXCLUDED.acl_groups,
                        updated_at = now()
                    """,
                    project_id, key, json.dumps(value), caller_sub, agent, session_id, classification, json.dumps([]),
                )
                facts_written += 1

            for memory in memories:
                text = memory["text"]
                kind = memory.get("kind", "fact")
                embedding = await embed_query(text)
                # ADR-0209: source URL for a project memory is synthetic
                # (there is no external document it came from) - stable
                # per (project_id, session, kind, text) so re-extracting
                # the identical fact from the same session is idempotent
                # (ON CONFLICT below), while a genuinely new fact/session
                # gets its own row.
                source = f"project-memory://{project_id}/{session_id or 'no-session'}/{_memory_id_for(text)}"
                metadata = {
                    "domain": _PROJECT_DOMAIN,
                    "project_id": project_id,
                    "agent": agent,
                    "session_id": session_id,
                    "memory_kind": kind,
                    "source_type": "project-extraction",
                    "classification": classification,
                    "acl_groups": [],
                    "provenance": "agent-runtime memory extraction",
                    "indexed_at": _utcnow_iso(),
                }
                await conn.execute(
                    """
                    INSERT INTO document_embeddings (source, chunk_index, title, content, embedding, metadata)
                    VALUES ($1, 0, $2, $3, $4, $5::jsonb)
                    ON CONFLICT (source, chunk_index) DO UPDATE SET
                        title = EXCLUDED.title,
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata,
                        updated_at = now()
                    """,
                    source, f"{kind}: {project_id}", text, embedding, json.dumps(metadata),
                )
                memories_written += 1

    logger.info(
        "project-memory write: project_id=%s agent=%s facts=%d memories=%d",
        project_id, agent, facts_written, memories_written,
    )
    return {"facts_written": facts_written, "memories_written": memories_written}
