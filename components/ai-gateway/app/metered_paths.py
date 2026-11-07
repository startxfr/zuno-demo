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
    """Text of a Responses content value: a string, or parts carrying `text`
    (input_text, output_text, text, reasoning_text, summary_text) or `refusal`."""
    if isinstance(content, str):
        return [content]
    out: List[str] = []
    for part in content if isinstance(content, list) else []:
        if not isinstance(part, dict):
            continue
        if isinstance(part.get("text"), str):
            out.append(part["text"])
        elif isinstance(part.get("refusal"), str):
            out.append(part["refusal"])
    return out


def _output_texts(output: Any) -> List[str]:
    return [output] if isinstance(output, str) else _part_texts(output)


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
                items.extend(ScanItem("tool_result", t) for t in _output_texts(entry["output"]))
    return [it for it in items if it.text.strip()]


def system_scan_items(api: str, body: Dict[str, Any]) -> List[ScanItem]:
    """The caller's system-level text: Anthropic `system`; Responses `instructions`
    and `system`/`developer` input messages. Scanned in block mode only, since a
    client may put retrieved context there (ADR-0602 clause 8)."""
    texts: List[str] = []
    if api == ANTHROPIC:
        texts = _block_texts(body.get("system"))
    else:
        if isinstance(body.get("instructions"), str):
            texts.append(body["instructions"])
        raw = body.get("input")
        for entry in raw if isinstance(raw, list) else []:
            if isinstance(entry, dict) and entry.get("role") in ("system", "developer"):
                texts.extend(_part_texts(entry.get("content")))
    return [ScanItem("system", t) for t in texts if t.strip()]


def scan_items(api: str, body: Dict[str, Any], include_system: bool = False) -> List[ScanItem]:
    items = anthropic_scan_items(body) if api == ANTHROPIC else responses_scan_items(body)
    return items + system_scan_items(api, body) if include_system else items


class _Message:
    """A ChatMessage-like view (role, content) for app/tool_markers.py."""

    def __init__(self, role: str, content: str):
        self.role, self.content = role, content


def marker_messages(api: str, body: Dict[str, Any]) -> List[_Message]:
    """Every tool result of the request, as a `tool` message, so app/tool_markers.py
    reads the ADR-0594 markers the mcp-gateway signed into it, with the same raise
    and fail-closed rules as on chat. Documents and search results are user-supplied,
    not tool output: their markers raise, but an unmarked one is not a tool result."""
    out: List[_Message] = []
    if api == ANTHROPIC:
        for m in body.get("messages") or []:
            if not isinstance(m, dict) or not isinstance(m.get("content"), list):
                continue
            for block in m["content"]:
                if not isinstance(block, dict):
                    continue
                kind = block.get("type")
                if kind == "tool_result":
                    out.append(_Message("tool", "\n\n".join(_block_texts(block.get("content")))))
                elif kind == "document":
                    out.append(_Message("user", "\n\n".join(_anthropic_document_text(block))))
                elif kind == "search_result":
                    out.append(_Message("user", "\n\n".join(_block_texts(block.get("content")))))
    else:
        raw = body.get("input")
        for entry in raw if isinstance(raw, list) else []:
            if isinstance(entry, dict) and str(entry.get("type") or "").endswith("_call_output"):
                out.append(_Message("tool", "\n\n".join(_output_texts(entry.get("output")))))
    return out


def request_problem(api: str, body: Dict[str, Any]) -> Optional[str]:
    """A Responses request the pass-through refuses: state kept upstream would escape
    the gateway's scan and metering (background runs, stored responses chained by id)."""
    if api != RESPONSES:
        return None
    if body.get("background"):
        return "background responses are not served on this path"
    if body.get("previous_response_id"):
        return "previous_response_id is not served on this path: send the whole input"
    if body.get("conversation"):
        return "conversation state is not served on this path: send the whole input"
    return None


def upstream_body(api: str, body: Dict[str, Any], model: str) -> Dict[str, Any]:
    out = {**body, "model": model}
    if api == RESPONSES:
        out["store"] = False  # nothing kept upstream, nothing to chain to later
    return out


def estimate_prompt_tokens(api: str, body: Dict[str, Any]) -> int:
    """Four characters per token over what the model reads, for a call whose
    upstream reported no usage (a disconnect, a cut, a missing final event)."""
    keys = ("system", "messages", "tools") if api == ANTHROPIC else ("instructions", "input", "tools")
    return len(json.dumps({k: body.get(k) for k in keys if k in body})) // 4 + 1


def requested_output_tokens(api: str, body: Dict[str, Any]) -> int:
    value = body.get("max_tokens" if api == ANTHROPIC else "max_output_tokens")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


# ---------------------------------------------------------------------------
# The reply: its text (for guardrails) and its usage (for metering).

def _anthropic_block_text(block: Any) -> str:
    if not isinstance(block, dict):
        return ""
    kind = block.get("type")
    if kind == "text":
        return block.get("text") or ""
    if kind == "thinking":
        return block.get("thinking") or ""
    if kind in ("tool_use", "server_tool_use"):
        return json.dumps(block.get("input") or {}) if block.get("input") else ""
    return "\n".join(_strings(block))


def _responses_item_text(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    kind = item.get("type")
    if kind == "message":
        return "\n".join(_part_texts(item.get("content")))
    if kind == "function_call":
        return str(item.get("arguments") or "")
    if kind == "reasoning":
        return "\n".join(_part_texts(item.get("content")) + _part_texts(item.get("summary")))
    return "\n".join(_strings(item))


def reply_text(api: str, payload: Dict[str, Any]) -> str:
    """Everything the caller is shown: text, tool-call arguments and reasoning."""
    if api == ANTHROPIC:
        parts = [_anthropic_block_text(b) for b in payload.get("content") or []]
    else:
        parts = [_responses_item_text(i) for i in payload.get("output") or []]
    return "\n".join(p for p in parts if p)


# Keys whose string values are text a client renders; read from an event or
# an item of a type this module does not know, so a new type is scanned too.
_TEXT_KEYS = ("text", "delta", "thinking", "partial_json", "arguments", "refusal", "content", "output",
              "summary")
# Metadata of a known shape that carries no model text.
_SKIP_KEYS = ("id", "type", "model", "role", "status", "object", "signature", "call_id", "name",
              "item_id", "stop_reason", "stop_sequence", "usage", "metadata", "instructions", "tools")


def _strings(value: Any, depth: int = 0) -> List[str]:
    if depth > 6:
        return []
    out: List[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _SKIP_KEYS:
                continue
            if isinstance(item, str):
                if key in _TEXT_KEYS:
                    out.append(item)
            else:
                out.extend(_strings(item, depth + 1))
    elif isinstance(value, list):
        for item in value:
            out.extend(_strings(item, depth + 1))
    return out


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


# Event types known to carry no model text (anything else is scanned).
_ANTHROPIC_SILENT = {"message_start", "message_delta", "message_stop", "content_block_stop", "ping", "error"}
_RESPONSES_SILENT = {"response.created", "response.in_progress", "response.queued", "error",
                     "response.output_item.added", "response.content_part.added"}
_RESPONSES_DELTAS = {"response.output_text.delta", "response.function_call_arguments.delta",
                     "response.reasoning_text.delta", "response.reasoning_summary_text.delta",
                     "response.refusal.delta"}


class StreamMeter:
    """Reads the usage and the reply text out of the upstream's SSE events.

    `observe` returns the text an event shows the caller, for the guard: deltas,
    reasoning deltas, the text of a content block start, the full text a `.done`
    or `response.completed` event repeats (scanned again: an upstream could send
    something else there), and the string content of an unknown event type.
    `generated` counts the delta text only, for the completion estimate."""

    def __init__(self, api: str):
        self.api = api
        self.prompt = 0
        self.completion = 0
        self.usage_seen = False
        self.generated = 0

    def _usage(self, pair: Tuple[int, int]) -> None:
        if pair[0] or pair[1]:
            self.usage_seen = True
        self.prompt = max(self.prompt, pair[0])
        self.completion = max(self.completion, pair[1])

    def observe(self, data: Any) -> str:
        """Record usage carried by one event; return the reply text it shows."""
        if not isinstance(data, dict):
            return ""
        kind = data.get("type")
        if self.api == ANTHROPIC:
            if kind == "message_start":
                message = data.get("message") or {}
                self._usage(anthropic_usage(message.get("usage")))
                return "\n".join(t for t in (_anthropic_block_text(b) for b in message.get("content") or []) if t)
            if kind == "message_delta":
                # output_tokens is cumulative; a recent API repeats input_tokens here.
                self._usage(anthropic_usage(data.get("usage")))
                return ""
            if kind in _ANTHROPIC_SILENT:
                return ""
            if kind == "content_block_start":
                return _anthropic_block_text(data.get("content_block"))
            if kind == "content_block_delta":
                delta = data.get("delta") or {}
                text = {"text_delta": delta.get("text"), "input_json_delta": delta.get("partial_json"),
                        "thinking_delta": delta.get("thinking")}.get(delta.get("type"))
                if delta.get("type") == "signature_delta":
                    return ""
                if text is None:
                    text = "\n".join(_strings(delta))
                self.generated += len(text or "")
                return text or ""
            return "\n".join(_strings(data))
        if kind in ("response.completed", "response.incomplete", "response.failed"):
            response = data.get("response") or {}
            self._usage(responses_usage(response.get("usage")))
            return reply_text(RESPONSES, response)
        if kind in _RESPONSES_SILENT:
            return ""
        if kind in _RESPONSES_DELTAS:
            delta = data.get("delta")
            text = delta if isinstance(delta, str) else ""
            self.generated += len(text)
            return text
        if kind == "response.output_item.done":
            return _responses_item_text(data.get("item"))
        if kind == "response.content_part.done":
            return "\n".join(_part_texts([data.get("part")]))
        return "\n".join(_strings({k: v for k, v in data.items() if k != "response"}))


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
