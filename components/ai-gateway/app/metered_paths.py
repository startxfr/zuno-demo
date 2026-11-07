"""ADR-0602 clause 9 (WP-225 lot A): `/v1/messages` and `/v1/responses` metered in the ai-gateway.

MaaS 3.6 counts tokens on `/v1/chat/completions` and `/v1/embeddings` only
(Limitador reads `usage.total_tokens`); an Anthropic Messages reply reports
`input_tokens` and `output_tokens`, a Responses reply its own `usage`, so both
paths are uncounted there (WP-220 section 9). A TokenRateLimitPolicy data-
extraction rule cannot add two fields, and maas-controller rewrites the policy
spec on every reconcile, so the counting is done here.

The gateway serves both paths as a metered pass-through: the request body is
forwarded verbatim (the `model` rewritten to the served name) to a LOCAL model's
endpoint that speaks the protocol (vLLM does, directly or through MaaS, as
WP-220 proved for gpt-oss-20b), and the reply's usage is counted on the same
path as a chat call: the `zuno.model_tokens` counters of app/telemetry.py and
the token-budget ledger of app/quota.py, plus the optional per-key ceiling of
app/key_ceilings.py. The paths are never blocked by the metering itself: no
ceiling is configured unless the chart sets one.

Off by default (METERED_PATHS_ENABLED, chart `meteredPaths.enabled`): the
endpoints answer 404 as they do today. Which models are served comes from
METERED_PATHS_MODELS (chart `meteredPaths.models`), a JSON object mapping the
`model` a client sends to provider-routing.yaml provider names, tried in order:
the first one eligible for the request's effective classification (WP-209) and
reachable is used. Only `kind: local` providers with an `endpoint` are accepted:
a SaaS key is never handed to a pass-through.

This module holds the protocol knowledge (what to scan, where the usage is,
the error envelopes); app/main.py holds the two endpoints.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence, Tuple

from fastapi.responses import JSONResponse

from app.guardrails import ScanItem, scan_tool_results

logger = logging.getLogger("ai_gateway.metered_paths")

ANTHROPIC = "anthropic-messages"
RESPONSES = "openai-responses"
_PATHS = {ANTHROPIC: "/messages", RESPONSES: "/responses"}
# Request headers forwarded to the upstream as they are (the protocol's own).
FORWARDED_HEADERS = ("anthropic-version", "anthropic-beta")


def enabled() -> bool:
    return os.getenv("METERED_PATHS_ENABLED", "false").strip().lower() == "true"


def model_map() -> Dict[str, List[str]]:
    raw = os.getenv("METERED_PATHS_MODELS", "")
    if not raw.strip():
        return {}
    try:
        doc = json.loads(raw)
    except ValueError:
        logger.error("ignoring malformed METERED_PATHS_MODELS: %r", raw)
        return {}
    if not isinstance(doc, dict):
        logger.error("METERED_PATHS_MODELS must be a JSON object: %r", raw)
        return {}
    out: Dict[str, List[str]] = {}
    for model, providers in doc.items():
        names = [providers] if isinstance(providers, str) else list(providers or [])
        out[str(model)] = [str(n) for n in names if n]
    return out


def upstream_url(cfg: Dict[str, Any], api: str, suffix: str = "") -> str:
    """The provider's `.../v1` endpoint plus the protocol path."""
    return cfg["endpoint"].rstrip("/") + _PATHS[api] + suffix


# ---------------------------------------------------------------------------
# Error envelopes, per protocol.

def anthropic_error(status: int, err_type: str, message: str, headers: Optional[Dict[str, str]] = None,
                    **extra: Any) -> JSONResponse:
    return JSONResponse({"type": "error", "error": {"type": err_type, "message": message, **extra}},
                        status_code=status, headers=headers)


def openai_error(status: int, err_type: str, code: str, message: str,
                 headers: Optional[Dict[str, str]] = None, **extra: Any) -> JSONResponse:
    return JSONResponse({"error": {"message": message, "type": err_type, "param": None, "code": code, **extra}},
                        status_code=status, headers=headers)


def error(api: str, status: int, code: str, message: str,
          headers: Optional[Dict[str, str]] = None, **extra: Any) -> JSONResponse:
    """One gateway error in the envelope of `api`. `code` is the gateway's own
    (guardrails_blocked, rate_limit_exceeded, ...); the protocol type follows the status."""
    if api == ANTHROPIC:
        err_type = {400: "invalid_request_error", 404: "not_found_error", 429: "rate_limit_error",
                    503: "api_error"}.get(status, "api_error")
        return anthropic_error(status, err_type, message, headers, code=code, **extra)
    err_type = {400: "invalid_request_error", 404: "invalid_request_error", 429: "tokens",
                503: "server_error"}.get(status, "server_error")
    return openai_error(status, err_type, code, message, headers, **extra)


# ---------------------------------------------------------------------------
# What guardrails scan on the request (ADR-0602 clause 8).

def _block_texts(content: Any) -> List[str]:
    """Text of an Anthropic content value: a string, or a list of blocks of which
    the `text` ones count."""
    if isinstance(content, str):
        return [content]
    out: List[str] = []
    for block in content if isinstance(content, list) else []:
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
            out.append(block["text"])
    return out


def _anthropic_document_text(block: Dict[str, Any]) -> List[str]:
    source = block.get("source") or {}
    if source.get("type") == "text" and isinstance(source.get("data"), str):
        return [source["data"]]
    if source.get("type") == "content":
        return _block_texts(source.get("content"))
    return []


def anthropic_scan_items(body: Dict[str, Any]) -> List[ScanItem]:
    """The last user message with text (the prompt), then the tool_result,
    document and search_result blocks from that message on (the current turn)."""
    messages = [m for m in body.get("messages") or [] if isinstance(m, dict)]
    start = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user" and any(t.strip() for t in _block_texts(messages[i].get("content"))):
            start = i
            break
    items: List[ScanItem] = []
    if start is not None:
        items.extend(ScanItem("prompt", t) for t in _block_texts(messages[start].get("content")))
    if scan_tool_results():
        for m in messages[start if start is not None else 0:]:
            if m.get("role") != "user" or not isinstance(m.get("content"), list):
                continue
            for block in m["content"]:
                if not isinstance(block, dict):
                    continue
                kind = block.get("type")
                if kind == "tool_result":
                    items.extend(ScanItem("tool_result", t) for t in _block_texts(block.get("content")))
                elif kind == "document":
                    items.extend(ScanItem("retrieved", t) for t in _anthropic_document_text(block))
                elif kind == "search_result":
                    items.extend(ScanItem("retrieved", t) for t in _block_texts(block.get("content")))
    return [it for it in items if it.text.strip()]


def _part_texts(content: Any) -> List[str]:
    """Text of a Responses content value: a string, or parts of type input_text/output_text/text."""
    if isinstance(content, str):
        return [content]
    out: List[str] = []
    for part in content if isinstance(content, list) else []:
        if isinstance(part, dict) and part.get("type") in ("input_text", "output_text", "text") \
                and isinstance(part.get("text"), str):
            out.append(part["text"])
    return out


def responses_scan_items(body: Dict[str, Any]) -> List[ScanItem]:
    """`input` as a string is the prompt; as a list, the last user message is
    the prompt and every tool output item after it a tool result."""
    raw = body.get("input")
    if isinstance(raw, str):
        return [ScanItem("prompt", raw)] if raw.strip() else []
    entries = [e for e in raw or [] if isinstance(e, dict)] if isinstance(raw, list) else []
    start = None
    for i in range(len(entries) - 1, -1, -1):
        if entries[i].get("role") == "user":
            start = i
            break
    items: List[ScanItem] = []
    if start is not None:
        items.extend(ScanItem("prompt", t) for t in _part_texts(entries[start].get("content")))
    if scan_tool_results():
        for entry in entries[(start + 1) if start is not None else 0:]:
            kind = str(entry.get("type") or "")
            if kind.endswith("_call_output") and "output" in entry:
                output = entry["output"]
                texts = [output] if isinstance(output, str) else _part_texts(output)
                items.extend(ScanItem("tool_result", t) for t in texts)
    return [it for it in items if it.text.strip()]


def scan_items(api: str, body: Dict[str, Any]) -> List[ScanItem]:
    return anthropic_scan_items(body) if api == ANTHROPIC else responses_scan_items(body)


# ---------------------------------------------------------------------------
# The reply: its text (for guardrails) and its usage (for metering).

def reply_text(api: str, payload: Dict[str, Any]) -> str:
    parts: List[str] = []
    if api == ANTHROPIC:
        for block in payload.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                parts.append(block.get("text") or "")
            elif block.get("type") == "tool_use":
                parts.append(json.dumps(block.get("input") or {}))
    else:
        for item in payload.get("output") or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message":
                parts.extend(_part_texts(item.get("content")))
            elif item.get("type") == "function_call":
                parts.append(str(item.get("arguments") or ""))
    return "\n".join(p for p in parts if p)


def _int(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def anthropic_usage(usage: Any) -> Tuple[int, int]:
    """(prompt, completion) of an Anthropic `usage`: cache writes and reads are
    prompt tokens too (they are read by the model and billed)."""
    usage = usage if isinstance(usage, dict) else {}
    prompt = _int(usage.get("input_tokens")) + _int(usage.get("cache_creation_input_tokens")) \
        + _int(usage.get("cache_read_input_tokens"))
    return prompt, _int(usage.get("output_tokens"))


def responses_usage(usage: Any) -> Tuple[int, int]:
    usage = usage if isinstance(usage, dict) else {}
    prompt, completion = _int(usage.get("input_tokens")), _int(usage.get("output_tokens"))
    if not prompt and not completion and _int(usage.get("total_tokens")):
        return _int(usage.get("total_tokens")), 0
    return prompt, completion


def usage_of(api: str, payload: Dict[str, Any]) -> Tuple[int, int]:
    if api == ANTHROPIC:
        return anthropic_usage(payload.get("usage"))
    return responses_usage(payload.get("usage"))


class StreamMeter:
    """Reads the usage and the reply text out of the upstream's SSE events."""

    def __init__(self, api: str):
        self.api = api
        self.prompt = 0
        self.completion = 0

    def observe(self, data: Any) -> str:
        """Record usage carried by one event; return the reply text it adds."""
        if not isinstance(data, dict):
            return ""
        kind = data.get("type")
        if self.api == ANTHROPIC:
            if kind == "message_start":
                prompt, completion = anthropic_usage((data.get("message") or {}).get("usage"))
                self.prompt = max(self.prompt, prompt)
                self.completion = max(self.completion, completion)
            elif kind == "message_delta":
                # output_tokens is cumulative; a recent API repeats input_tokens here.
                prompt, completion = anthropic_usage(data.get("usage"))
                self.prompt = max(self.prompt, prompt)
                self.completion = max(self.completion, completion)
            elif kind == "content_block_delta":
                delta = data.get("delta") or {}
                if delta.get("type") == "text_delta":
                    return delta.get("text") or ""
                if delta.get("type") == "input_json_delta":
                    return delta.get("partial_json") or ""
            return ""
        if kind in ("response.completed", "response.incomplete", "response.failed"):
            self.prompt, self.completion = responses_usage((data.get("response") or {}).get("usage"))
        elif kind in ("response.output_text.delta", "response.function_call_arguments.delta"):
            delta = data.get("delta")
            return delta if isinstance(delta, str) else ""
        return ""


async def sse_events(lines: AsyncIterator[str]) -> AsyncIterator[Tuple[str, Any]]:
    """Group upstream SSE lines into events: (raw event text, parsed data or None)."""
    buf: List[str] = []
    async for line in lines:
        if line == "":
            if buf:
                yield _event(buf)
                buf = []
            continue
        buf.append(line)
    if buf:
        yield _event(buf)


def _event(lines: Sequence[str]) -> Tuple[str, Any]:
    data_lines = [ln[5:].lstrip() if ln.startswith("data:") else None for ln in lines]
    data_text = "\n".join(d for d in data_lines if d is not None)
    try:
        data = json.loads(data_text) if data_text else None
    except ValueError:
        data = None
    return "\n".join(lines) + "\n\n", data
