"""ADR-0594: a signed classification marker on every tool result of /mcp.

The ai-gateway reads these markers in the messages of a model call and raises the
call's classification (ADR-0034), making it local-only when the tool forbids
external context (ADR-0035). The marker is one text line appended to the result:

    [zuno-classification level=C2 external=0 sig=<hex>]

`sig` is HMAC-SHA256 over "<level>|<external>|<sha256 of the stripped text the
line follows>", with the key in ZUNO_MARKER_KEY, shared with the ai-gateway
(same format in components/ai-gateway/app/tool_markers.py). No key, no marker:
the ai-gateway then treats an experience client's tool results as unmarked (C2,
local-only), the safe direction.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any, Iterable, Optional

LEVELS = ("C1", "C2", "C3", "C4")
_RANK = {level: i for i, level in enumerate(LEVELS, start=1)}


def _key() -> bytes:
    return os.getenv("ZUNO_MARKER_KEY", "").strip().encode("utf-8")


def enabled() -> bool:
    return bool(_key())


def highest(levels: Iterable[Optional[str]]) -> str:
    best = "C1"
    for level in levels:
        value = str(level or "").strip().upper()
        if value in _RANK and _RANK[value] > _RANK[best]:
            best = value
    return best


def levels_in(payload: Any, _depth: int = 0) -> Iterable[str]:
    """Every `classification` value found in a tool result (the RAG chunks of
    WP-187 carry one per result)."""
    if _depth > 6:
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "classification" and isinstance(value, str):
                yield value
            else:
                yield from levels_in(value, _depth + 1)
    elif isinstance(payload, list):
        for item in payload:
            yield from levels_in(item, _depth + 1)


def signature(level: str, external: bool, text: str, key: Optional[bytes] = None) -> str:
    digest = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
    message = f"{level}|{1 if external else 0}|{digest}".encode("utf-8")
    return hmac.new(key if key is not None else _key(), message, hashlib.sha256).hexdigest()


def marker_line(level: str, external: bool, text: str) -> str:
    return f"[zuno-classification level={level} external={1 if external else 0} sig={signature(level, external, text)}]"


def mark(text: str, level: str, external: bool) -> str:
    """The result text with its marker line, or the text unchanged without a key."""
    if not enabled():
        return text
    return f"{text}\n\n{marker_line(level, external, text)}"
