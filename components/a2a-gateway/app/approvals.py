"""Human approval across a delegation (ADR-0409 clause 2, WP-173 step 5).

The target raises an approval as the A2A task state `input-required`, with the request in
`status.message.metadata["zuno.approval"]`. The initiating user's side answers with a message on the same task
carrying a data part `{"zuno.approval": {request_id, decision, feedback}}`. A pending approval lives in this
process only (no persistence across a restart, decided 2026-11-05) and a silence is a refusal: the A2A SDK ends
the turn at `input-required`, the state needed to go on is kept here, and an answer that comes after the 300 seconds
(or after a restart) finds nothing to resume and runs nothing.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

APPROVAL_KEY = "zuno.approval"
APPROVAL_TIMEOUT_SECONDS = 300.0
DECISIONS = ("approve", "reject")  # modify / redirect are not served in v1 and count as a refusal

_SENSITIVE = re.compile(r"token|secret|password|passwd|credential|api[-_]?key|authorization", re.I)


def redact_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """A short, safe summary of tool arguments for the user to read (never a secret, never a long blob)."""
    summary: Dict[str, Any] = {}
    for key, value in list(arguments.items())[:20]:
        if _SENSITIVE.search(str(key)):
            summary[str(key)] = "***"
        else:
            text = value if isinstance(value, str) else repr(value)
            summary[str(key)] = text if len(text) <= 200 else text[:200] + "..."
    return summary


@dataclass
class PendingApproval:
    """Everything needed to go on with a turn once the user has answered."""

    request_id: str
    caller_sub: str
    task: str
    classification: str
    run_id: str
    chain_headers: Dict[str, str]
    messages: List[Dict[str, Any]]
    backlog: List[Dict[str, Any]]  # tool calls still to run; the first one awaits the answer
    rounds_left: int
    expires_at: float = field(default_factory=lambda: time.monotonic() + APPROVAL_TIMEOUT_SECONDS)


class PendingStore:
    """The pending approvals of one agent endpoint, keyed by task id."""

    def __init__(self) -> None:
        self._pending: Dict[str, PendingApproval] = {}

    def put(self, task_id: str, pending: PendingApproval) -> None:
        now = time.monotonic()
        for key in [k for k, v in self._pending.items() if v.expires_at < now]:
            del self._pending[key]
        self._pending[task_id] = pending

    def take(self, task_id: str, request_id: str) -> Optional[PendingApproval]:
        """The pending approval for this answer, removed from the store; None when absent, expired or not this request."""
        pending = self._pending.get(task_id)
        if pending is None or pending.request_id != request_id:
            return None
        del self._pending[task_id]
        return None if pending.expires_at < time.monotonic() else pending

    def drop(self, task_id: str) -> None:
        self._pending.pop(task_id, None)


def answer_in(message: Any) -> Optional[Dict[str, Any]]:
    """The approval answer carried by a data part of the message, if any."""
    for part in getattr(message, "parts", None) or []:
        data = getattr(getattr(part, "root", part), "data", None)
        if isinstance(data, dict) and isinstance(data.get(APPROVAL_KEY), dict):
            return data[APPROVAL_KEY]
    return None
