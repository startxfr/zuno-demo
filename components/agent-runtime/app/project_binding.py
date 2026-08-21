"""ADR-0512/WP-55: pre-graph project-binding verification.

For a `project_required` task, app/main.py's agent_chat must resolve a
caller-supplied candidate project (name or Salesforce opportunity id) into
a verified project_id before a graph is ever built or invoked - this
module is that standalone verification step, never routed through
app/graph/nodes.py's tool_call_node, so it never populates tool_results/
citations/the model's own context. That distinction matters: Comage's own
salesforce MCP server module docstring frames `salesforce.opportunity.read`
as "Comage's live Salesforce integration", and Finage's
answer-finance-question prompt explicitly disclaims live Salesforce access
(ADR-0326) - a project-binding yes/no decision is not the same as
surfacing Salesforce record content to a Finage answer, so this module
returns only a verified id, never a result's title/stage/amount/etc.

Verification rides the MCP Gateway's existing salesforce.opportunity.read
capability, called through app/clients/mcp_client.invoke_tool under the
caller's own bearer token (ADR-0013 propagation) - the same authorization
path every other tool call already uses, never a new one. The MCP
Gateway itself needs zero changes (ADR-0512's own "what NOT to touch" -
verification rides the existing ADR-0011/ADR-0036 intersection unchanged).

This module never touches a database - app/conversations.py owns caching
the verified binding on the conversation row and deciding when a cached
binding is stale enough to re-verify (is_binding_still_valid below is the
pure function that decision is based on); keeping this module pool-free
mirrors app/clients/mcp_client.py's own scope.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import yaml

from app.clients import mcp_client

logger = logging.getLogger("agent_runtime.project_binding")

QUOTA_POLICY_PATH = os.getenv("QUOTA_POLICY_PATH", "/app/policies/quotas/quota-policy.yaml")

# Same small window-string parser as components/ai-gateway/app/quota.py's
# _window_seconds - duplicated rather than shared, matching this repo's own
# convention of duplicating small well-specified logic across independently
# deployed services rather than introducing a shared package for one field.
_WINDOW_RE = re.compile(r"^([0-9]+)(s|m|h|d)$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}

# Standard Salesforce Opportunity key prefix ("006"), 15 or 18 chars,
# alphanumeric - permissive enough to route by shape without needing a
# real Salesforce schema fetch.
_SALESFORCE_ID_RE = re.compile(r"^006[a-zA-Z0-9]{12,15}$")


class ProjectBindingError(Exception):
    """Base for every fail-closed project-binding outcome (ADR-0512 clause
    3) - app/main.py maps each subclass to a distinct HTTP status so a
    Salesforce outage is observably different from an authorization
    denial, per the ADR's own Operational considerations."""


class ProjectCandidateMissingError(ProjectBindingError):
    """No candidate project (name or Salesforce id) was supplied for a
    project_required task. The prompt asks for one (ADR-0512 clause 2),
    but enforcement is this server-side check, not the model's
    cooperation - a user who never answers the prompt is blocked here."""


class ProjectNotFoundError(ProjectBindingError):
    """cause: unknown_project - zero matches, or several with no exact
    title match. Ambiguous multi-match deliberately folds into this cause
    rather than inventing a fourth one: the platform's cause taxonomy
    stays exactly the three ADR-0512/WP-55 name (unknown project / no
    access / unreachable)."""


class ProjectAccessDeniedError(ProjectBindingError):
    """cause: no_access - the MCP Gateway's ADR-0011 policy intersection
    denied the caller's own identity (a 403 from mcp_client), independent
    of whether the named project exists at all."""


class ProjectBindingUnreachableError(ProjectBindingError):
    """cause: unreachable - a transport-level failure (timeout, connection
    refused, DNS) or any non-403 HTTP error talking to the MCP Gateway/
    Salesforce. Fail-closed like the other two causes: a Salesforce outage
    pauses project-bound work rather than degrading it to unverified."""


def _window_seconds(window: str) -> int:
    match = _WINDOW_RE.match(str(window))
    if not match:
        raise ValueError(f"unparseable window {window!r}")
    return int(match.group(1)) * _UNIT_SECONDS[match.group(2)]


def _load_validity_window_seconds(path: str = QUOTA_POLICY_PATH) -> int:
    """A missing/malformed quota-policy.yaml must not silently widen the
    re-verification window (that would be fail-OPEN on a security check,
    the opposite of every other policy-load failure in this codebase) -
    it falls back to 0 seconds, meaning every turn re-verifies against
    Salesforce until the file is present and correct, never to caching
    indefinitely."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        window = (doc.get("project_binding") or {}).get("validity_window")
        if not window:
            return 0
        return _window_seconds(window)
    except Exception as exc:
        logger.error("failed to load project_binding.validity_window from %s: %s", path, exc)
        return 0


VALIDITY_WINDOW_SECONDS = _load_validity_window_seconds()


def is_binding_still_valid(verified_at: Optional[datetime]) -> bool:
    """ADR-0512 clause 3: "re-verified on resume after a policy-defined
    validity window" - app/main.py calls this against a cached binding's
    project_id_verified_at (app/conversations.py) to decide whether this
    turn can skip a fresh Salesforce call."""
    if verified_at is None:
        return False
    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - verified_at).total_seconds()
    return age_seconds < VALIDITY_WINDOW_SECONDS


def _looks_like_salesforce_id(candidate: str) -> bool:
    return bool(_SALESFORCE_ID_RE.match(candidate.strip()))


def _select_match(candidate: str, results: List[Dict[str, Any]]) -> Optional[str]:
    """read_opportunity is search-shaped, not an exact-id lookup
    (components/mcp-servers/salesforce/server.py): {query, results:
    [{id, title, ...}], count}. An id-shaped candidate must match a
    result's id exactly; a name-shaped candidate must match a result's
    title exactly (case-insensitive) or be the sole unambiguous result.
    Returns None (unknown_project) for zero matches or an ambiguous
    multi-match with no exact title hit."""
    candidate_norm = candidate.strip()
    if _looks_like_salesforce_id(candidate_norm):
        for result in results:
            if result.get("id") == candidate_norm:
                return result["id"]
        return None

    exact_title_matches = [
        r for r in results if (r.get("title") or "").strip().lower() == candidate_norm.lower()
    ]
    if len(exact_title_matches) == 1:
        return exact_title_matches[0]["id"]
    if len(results) == 1:
        return results[0]["id"]
    return None


async def verify_project_binding(
    candidate: Optional[str],
    *,
    bearer_token: str,
    agent_name: str,
    task_name: str,
) -> str:
    """Calls salesforce.opportunity.read under the caller's own identity
    and returns the verified Salesforce Opportunity id, or raises one of
    the typed errors above - never returns an unverified value."""
    candidate = (candidate or "").strip()
    if not candidate:
        raise ProjectCandidateMissingError(
            "a project_required task needs a candidate project (name or Salesforce opportunity id)"
        )

    try:
        response = await mcp_client.invoke_tool(
            "salesforce.opportunity.read",
            {"query": candidate, "limit": 5},
            bearer_token=bearer_token,
            agent_name=agent_name,
            task_name=task_name,
            data_classification="C2",
        )
    except mcp_client.McpClientError as exc:
        if exc.status_code == 403:
            raise ProjectAccessDeniedError(
                f"caller is not authorized to read Salesforce opportunity {candidate!r}"
            ) from exc
        raise ProjectBindingUnreachableError(
            f"salesforce.opportunity.read unreachable while verifying {candidate!r}: {exc}"
        ) from exc

    results = response.get("results") or []
    matched_id = _select_match(candidate, results)
    if matched_id is None:
        raise ProjectNotFoundError(f"no verifiable Salesforce opportunity matches {candidate!r}")
    return matched_id
