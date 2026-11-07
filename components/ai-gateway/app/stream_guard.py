"""ADR-0602 clause 8 (WP-225 lot A): a streamed reply in `block` mode is held back and cut on a detection.

Before this, a streamed reply was only observed: every token reached the caller
and the detector saw the text after the stream ended. Now, in `block` mode, the
stream is forwarded in checked segments:

- events are held back until GUARDRAILS_STREAM_HOLD_BACK_CHARS characters of
  reply text are pending (chart `guardrails.streamHoldBackChars`, default 400);
- the pending text, with the last OVERLAP_CHARS already checked before it (so a
  pattern that straddles two segments is still seen), is evaluated;
- clean: the held events go out except those whose text reaches into the last
  OVERLAP_CHARS checked (the start of a match the next segment may complete);
  they go out after the next check, or after the end-of-stream check;
- detection: nothing unreleased goes out, the stream ends with the protocol's
  error event, and the upstream is closed;
- the detector unavailable: the segment goes out when the level fails open
  (below GUARDRAILS_FAIL_CLOSED_FROM), and the stream is cut when it fails closed.

A hold-back of 0 buffers the whole reply and checks it once, at the end.
Events that carry no reply text (a role delta, a ping, a usage chunk) go out at
once when nothing is held, so they never wait for text that may not come.

Protocol-agnostic: the caller passes the stream as (raw_event, text) pairs and a
function building the protocol's error event (OpenAI chat SSE, Anthropic SSE or
OpenAI Responses SSE; see the `*_error_event` helpers below).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("ai_gateway.stream_guard")

OVERLAP_CHARS = 256


def hold_back_chars() -> int:
    raw = os.getenv("GUARDRAILS_STREAM_HOLD_BACK_CHARS", "400")
    try:
        return max(0, int(raw))
    except ValueError:
        logger.error("GUARDRAILS_STREAM_HOLD_BACK_CHARS=%r is not an integer; using 400", raw)
        return 400


# evaluate(text) -> detections list, [] when clean, None when the detector is unavailable.
Evaluate = Callable[[str], Awaitable[Optional[List[Dict[str, Any]]]]]
# error_event(kind, detections) -> the raw text to send; kind is "blocked" or "unavailable".
ErrorEvent = Callable[[str, List[Dict[str, Any]]], str]


async def guard(
    events: AsyncIterator[Tuple[str, str]],
    *,
    evaluate: Evaluate,
    error_event: ErrorEvent,
    fail_closed: bool,
    on_cut: Optional[Callable[[str, List[Dict[str, Any]]], None]] = None,
) -> AsyncIterator[str]:
    """Yield the raw events of `events`, checked in segments; see the module docstring.

    Each held event remembers the reply offset its text ends at. A check covers
    the text from (checked - OVERLAP_CHARS) to the end, so a match straddling two
    segments is seen; and after a clean check only the events ending at or before
    (checked - OVERLAP_CHARS) are released, so the first part of such a match is
    never sent before the second part has been checked. The tail goes out after
    the end-of-stream check."""
    segment = hold_back_chars()
    held: List[Tuple[str, int]] = []  # (raw event, reply offset its text ends at)
    reply = ""      # the whole reply text so far
    checked = 0     # offset up to which the reply has been checked

    def releasable() -> List[str]:
        nonlocal held
        safe = max(0, checked - OVERLAP_CHARS)
        out: List[str] = []
        while held and held[0][1] <= safe:
            out.append(held.pop(0)[0])
        return out

    async def check() -> Optional[str]:
        """None when the reply so far is clean (or fails open), else the error event."""
        nonlocal checked
        if len(reply) <= checked:
            return None
        window = reply[max(0, checked - OVERLAP_CHARS):]
        checked = len(reply)
        if not window.strip():
            return None
        found = await evaluate(window)
        if found:
            if on_cut:
                on_cut("blocked", found)
            return error_event("blocked", found)
        if found is None and fail_closed:
            if on_cut:
                on_cut("unavailable", [])
            return error_event("unavailable", [])
        return None

    close = getattr(events, "aclose", None)
    try:
        async for raw, text in events:
            reply += text or ""
            held.append((raw, len(reply)))
            if segment and len(reply) - checked >= segment:
                cut = await check()
                if cut is not None:
                    yield cut
                    return
            # Events that end before anything unchecked (or in the clean, released
            # prefix) go out now, so a text-less event never waits for text.
            for item in releasable():
                yield item
        cut = await check()
        if cut is not None:
            yield cut
            return
        for item, _end in held:
            yield item
        held = []
    finally:
        if close is not None:
            try:
                await close()
            except Exception:  # noqa: BLE001 - closing the upstream never fails the stream
                logger.debug("closing the guarded upstream stream failed", exc_info=True)


def _names(detections: List[Dict[str, Any]]) -> List[str]:
    return sorted({str(d.get("detection")) for d in detections})


def _message(kind: str) -> str:
    if kind == "unavailable":
        return "the reply was cut: the guardrails detector is unavailable and this level fails closed"
    return "the reply was cut by the guardrails policy"


def openai_chat_error_event(kind: str, detections: List[Dict[str, Any]]) -> str:
    """OpenAI chat SSE: an `error` object chunk (the openai SDK raises APIError on
    it), then the stream terminator."""
    code = "guardrails_unavailable" if kind == "unavailable" else "guardrails_blocked"
    body = {"error": {"type": code, "code": code, "stage": "reply", "message": _message(kind),
                      "detections": _names(detections)}}
    return f"data: {json.dumps(body)}\n\ndata: [DONE]\n\n"


def anthropic_error_event(kind: str, detections: List[Dict[str, Any]]) -> str:
    """Anthropic Messages SSE: `event: error` with the API's error envelope."""
    body = {"type": "error", "error": {
        "type": "api_error" if kind == "unavailable" else "invalid_request_error",
        "message": _message(kind),
        "code": "guardrails_unavailable" if kind == "unavailable" else "guardrails_blocked",
        "stage": "reply", "detections": _names(detections),
    }}
    return f"event: error\ndata: {json.dumps(body)}\n\n"


def responses_error_event(kind: str, detections: List[Dict[str, Any]]) -> str:
    """OpenAI Responses SSE: `event: error` with type, code, message and param."""
    body = {"type": "error",
            "code": "guardrails_unavailable" if kind == "unavailable" else "guardrails_blocked",
            "message": _message(kind), "param": None, "detections": _names(detections)}
    return f"event: error\ndata: {json.dumps(body)}\n\n"
