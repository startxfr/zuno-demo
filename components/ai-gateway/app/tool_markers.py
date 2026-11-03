"""ADR-0594: read the signed classification markers the mcp-gateway appends to
tool results, and raise a model call from them (ADR-0034, ADR-0035).

A marker is one line, same format as components/mcp-gateway/app/classification_marker.py:

    [zuno-classification level=C2 external=0 sig=<hex>]

`sig` = HMAC-SHA256(ZUNO_MARKER_KEY, "<level>|<external>|<sha256 of the stripped
text before the line, back to the previous marker or the start of the message>").

Rules (ADR-0594 decision 3):
- a marker that verifies raises the call to its level and, with external=0,
  makes it local-only; a marker that does not verify is ignored;
- for a fail-closed client (the experience clients, MARKER_FAIL_CLOSED_CLIENTS),
  a `tool` message with no valid marker counts as C2 and local-only, and a call
  at C2 or above is local-only, since the external providers accept C2;
- nothing here can lower a classification or lift local-only.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

logger = logging.getLogger("ai_gateway.tool_markers")

_LINE = re.compile(r"\[zuno-classification level=(C[1-4]) external=([01]) sig=([0-9a-f]{64})\]")
_RANK = {"C1": 1, "C2": 2, "C3": 3, "C4": 4}
# The routing table knows C1 to C3; a C4 result is routed as C3, local-only.
_ROUTABLE_MAX = "C3"


def _key() -> bytes:
    return os.getenv("ZUNO_MARKER_KEY", "").strip().encode("utf-8")


def fail_closed_clients() -> List[str]:
    raw = os.getenv("MARKER_FAIL_CLOSED_CLIENTS", "open-webui,openclaw-*")
    return [c.strip() for c in raw.split(",") if c.strip()]


def is_fail_closed_client(azp: str) -> bool:
    for pattern in fail_closed_clients():
        if pattern.endswith("*"):
            if azp.startswith(pattern[:-1]) and len(azp) > len(pattern) - 1:
                return True
        elif azp == pattern:
            return True
    return False


@dataclass
class Assessment:
    classification: str
    local_only: bool
    reasons: List[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.reasons)


def _valid_markers(text: str, key: bytes) -> List[tuple]:
    """(level, external) of every marker in `text` whose signature verifies."""
    found = []
    start = 0
    for m in _LINE.finditer(text):
        level, external, sig = m.groups()
        body = text[start:m.start()]
        start = m.end()
        if not key:
            continue
        if _signed_suffix(body, level, external, sig, key):
            found.append((level, external == "1"))
    return found


def _signed_suffix(body: str, level: str, external: str, sig: str, key: bytes) -> bool:
    """True if the text just before the marker, starting at the message start
    or at any line start, is what was signed. A client may put the tool output
    after its own text (Open WebUI's prompt-based tool mode), so the signed text
    is a suffix of the body, not always all of it."""
    starts = [0] + [i + 1 for i, ch in enumerate(body) if ch == "\n"]
    for start in starts[-2000:]:
        digest = hashlib.sha256(body[start:].strip().encode("utf-8")).hexdigest()
        expected = hmac.new(key, f"{level}|{external}|{digest}".encode("utf-8"), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expected):
            return True
    return False


def _raise(current: str, level: str) -> str:
    return level if _RANK.get(level, 0) > _RANK.get(current, 0) else current


def assess(messages: Iterable, classification: str, local_only: bool, client: str) -> Assessment:
    """The classification and local-only flag of a call, raised from the markers
    in its messages. `messages` are ChatMessage-like (role, content)."""
    key = _key()
    fail_closed = is_fail_closed_client(client or "")
    result = Assessment(classification=classification, local_only=local_only)
    for message in messages or []:
        role = getattr(message, "role", None)
        content = getattr(message, "content", None)
        text = content if isinstance(content, str) else ""
        markers = _valid_markers(text, key) if text else []
        for level, external in markers:
            raised = _raise(result.classification, level)
            if raised != result.classification:
                result.reasons.append(f"marker {level}")
                result.classification = raised
            if not external and not result.local_only:
                result.local_only = True
                result.reasons.append("marker external=0")
        if fail_closed and role == "tool" and not markers:
            if _raise(result.classification, "C2") != result.classification:
                result.classification = "C2"
            if not result.local_only:
                result.local_only = True
            result.reasons.append("unmarked tool result")
    if fail_closed and _RANK.get(result.classification, 0) >= 2 and not result.local_only:
        result.local_only = True
        result.reasons.append(f"experience client at {result.classification}")
    if _RANK.get(result.classification, 0) > _RANK[_ROUTABLE_MAX]:
        result.classification = _ROUTABLE_MAX
        result.local_only = True
    return result
