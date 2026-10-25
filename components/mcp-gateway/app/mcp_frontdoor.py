"""Standard MCP streamable-HTTP front-door for the Zuno MCP Gateway (ADR-0524).

ADR-0043 made MCP this gateway's *south-side* protocol - the transport it uses
to reach `confluence-mcp`, `git-forge-mcp` and friends. Its *north* side has
always been a bespoke REST contract (`POST /v1/tools/{name}/invoke`), which no
standard MCP client can consume. OpenShift Lightspeed's `spec.mcpServers[]`
needs a real MCP endpoint, so this module adds one.

The deliberate design constraint: **this is a protocol adapter, not a second
authorization path.** Every request lands on the same `validate_token` ->
`evaluate()` -> `invoke_downstream()` chain `/v1/tools/{name}/invoke` uses. If
you find yourself adding a policy check here, or special-casing a caller, stop -
ADR-0036 exists specifically to keep the intersection in one place.

`tools/list` is derived from that same intersection rather than from a
hand-maintained list, so a caller only ever sees the tools it could actually
call. That is ADR-0524 clause 4's third enforcement layer, and it costs nothing
to keep correct because it is computed, not written down.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("mcp_gateway.frontdoor")

# ADR-0524: the capability allowlist that replaces ADR-0011's factors 1-2 for
# this endpoint.
#
# A standard MCP client has no OKF bundle, so it cannot satisfy
# agent_declaration/task_rights. Rather than give it a synthetic bundle, the
# reachable surface is pinned HERE, at deployment time. This is the stricter of
# the two: a bundle can be widened by editing Markdown under agents/ and
# re-syncing, whereas widening this requires a values change, an image rebuild
# or an explicit env override that shows up in the Deployment spec.
#
# Everything else still applies per caller: allowed_groups, min_classification
# and the caller's own groups are enforced for each capability below, so this
# list is a CEILING, never a grant. A user who may not read Confluence still
# cannot read it here.
DEFAULT_FRONTDOOR_CAPABILITIES = ("confluence.page.search", "confluence.page.read")

# ADR-0524 clause 4 says every capability reachable through this front-door
# is a read - true for every capability except this one. aap.cluster.audit
# (components/mcp-servers/aap/server.py's cluster_audit) launches a real AAP
# Job Template; it doesn't write platform data, but it isn't a pure read
# either, so it must not carry list_tools()'s otherwise-blanket
# readOnlyHint: true - Lightspeed's toolsApprovalConfig (tool_annotations)
# uses this hint to decide whether to prompt before calling.
_NON_READONLY_CAPABILITIES = {"aap.cluster.audit"}


def frontdoor_capabilities() -> List[str]:
    """The allowlist, overridable per deployment via a comma-separated env var.

    Empty or unset means the default read-only Confluence pair. An explicitly
    empty string disables the front-door's tool surface entirely, which is the
    intended kill switch: tools/list returns nothing and every tools/call is
    refused, without having to remove the endpoint.
    """
    raw = os.getenv("MCP_FRONTDOOR_CAPABILITIES")
    if raw is None:
        return list(DEFAULT_FRONTDOOR_CAPABILITIES)
    return [c.strip() for c in raw.split(",") if c.strip()]

@dataclass(frozen=True)
class Surface:
    """What one `/mcp` request may see and call, built by main.py (ADR-0571).

    `capabilities` is the exposed set and `decide(capability, binding)` returns
    the PolicyDecision for one of them. Both come from main.py, which owns the
    ADR-0011 intersection: this module only iterates and asks, it never decides.
    When a request carries no surface, the deployment-time ceiling below applies
    (`frontdoor_capabilities()` + factors 3-5), as for OpenShift Lightspeed.
    """

    capabilities: List[str]
    decide: Callable[[str, Any], Any]


# The MCP revision this front-door implements. Clients send their own in
# `initialize`; we echo ours back and let the client decide whether it can
# proceed, which is what the spec prescribes.
PROTOCOL_VERSION = "2025-06-18"

JSONRPC_VERSION = "2.0"

# JSON-RPC 2.0 reserved codes (https://www.jsonrpc.org/specification#error_object)
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class JsonRpcError(Exception):
    """A JSON-RPC-level failure (malformed request, unknown method).

    Deliberately distinct from a TOOL-level failure: an authorization denial or
    a downstream error is a successful JSON-RPC call whose *result* carries
    isError=true, per the MCP spec. Conflating the two makes a denied tool look
    like a broken server to the client, which is how a policy denial ends up
    being retried or reported as an outage.
    """

    def __init__(self, code: int, message: str, data: Optional[Any] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def _result(request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
    err: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": err}


def _tool_error(text: str) -> Dict[str, Any]:
    """A tool-level failure: a valid JSON-RPC result carrying isError."""
    return {"content": [{"type": "text", "text": text}], "isError": True}


def _tool_ok(payload: Any) -> Dict[str, Any]:
    """MCP requires `content` blocks. Downstream tools return structured JSON,
    so we send both: `structuredContent` for clients that can use it, and a
    text rendering for those that cannot. Lightspeed reads the text form.
    """
    import json as _json

    if isinstance(payload, str):
        text = payload
    else:
        try:
            text = _json.dumps(payload, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            text = str(payload)
    result: Dict[str, Any] = {"content": [{"type": "text", "text": text}], "isError": False}
    if isinstance(payload, dict):
        result["structuredContent"] = payload
    return result


# Models often name the search argument differently from the tool's own schema. Only the NAME of the
# argument is rewritten, and only for search capabilities; which tools the caller may use, the values it
# sends and the downstream authorization are untouched.
_QUERY_ALIASES = ("search_query", "q", "text", "query_text", "search_term", "keywords")
_MAX_ERROR_CHARS = 200


def _is_search(names: Any) -> bool:
    return any(str(n).rsplit(".", 1)[-1] == "search" or str(n).startswith("search_") for n in names)


# Arguments a search tool takes besides its text: never turned into the query.
_NON_QUERY_ARGUMENTS = frozenset({"space", "limit", "top_k", "source_type", "page_id", "id", "cursor", "offset"})


def normalise_arguments(names: Any, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Make a search call match its tool's schema when the model named the text argument differently.

    Applies only to search tools and only when `query` is absent or empty:
    1. the first of a few common aliases (`search_query`, `q`, `text`...) that carries a value becomes `query`;
    2. failing that, the one string argument that is not a known option (`space`, `limit`...) becomes `query`;
    3. a numeric string `limit` becomes an integer.
    Only names and the type of `limit` change; the values a caller sends and every authorization check do not.
    """
    if not _is_search(names):
        return arguments
    fixed = dict(arguments)
    if isinstance(fixed.get("limit"), str) and fixed["limit"].strip().isdigit():
        fixed["limit"] = int(fixed["limit"].strip())
    if not str(fixed.get("query", "")).strip():
        chosen = next(
            (a for a in _QUERY_ALIASES if isinstance(fixed.get(a), str) and fixed[a].strip()), None
        )
        if chosen is None:
            candidates = [
                k for k, v in fixed.items()
                if k != "query" and k not in _NON_QUERY_ARGUMENTS and isinstance(v, str) and v.strip()
            ]
            chosen = candidates[0] if len(candidates) == 1 else None
        if chosen is not None:
            value = fixed.pop(chosen)
            for alias in _QUERY_ALIASES:
                fixed.pop(alias, None)
            fixed["query"] = value
    return fixed


def _short_error(exc: Exception) -> str:
    """One short, neutral line for a tool failure: no stack, no validator dump, no documentation URL.

    A schema-validation failure becomes a plain instruction: some callers judge a raw validator message
    suspicious and abort the whole turn, and read an instruction aimed at the model the same way: the text
    describes what happened, it never tells the model what to do.
    """
    lines = [ln.strip() for ln in str(exc).splitlines() if ln.strip() and "errors.pydantic.dev" not in ln]
    text = lines[0] if lines else "the tool call failed"
    if "validation error" in text.lower():
        return "No result: the search arguments did not match the tool's schema."
    return text if len(text) <= _MAX_ERROR_CHARS else text[: _MAX_ERROR_CHARS - 1] + "\u2026"


def _input_schema(binding: Any) -> Dict[str, Any]:
    """Advertise an open object schema.

    We deliberately do NOT restate each downstream tool's argument schema here.
    Duplicating it would create a second contract that silently drifts from the
    MCP server that actually validates the call - and the downstream server
    already rejects bad arguments with a clear error. An open schema keeps this
    module a pure adapter.

    The one thing worth encoding is that arguments are an object, not an array,
    which is what every binding in platform/bindings/tools/tool-bindings.yaml
    expects.
    """
    return {"type": "object", "properties": {}, "additionalProperties": True}


def list_tools(
    *,
    policy_store: Any,
    binding_registry: Any,
    identity: Any,
    classification: str,
    surface: Optional[Surface] = None,
) -> List[Dict[str, Any]]:
    """Every capability this caller is actually authorized for, right now.

    Computed by running the SAME `evaluate()` the invoke path runs, once per
    known capability. That is a few hundred in-memory dict lookups, not a
    network call - cheap enough to do per request, and it means the advertised
    surface can never drift from the enforced one.
    """
    from app.policy import evaluate_without_declaration

    tools: List[Dict[str, Any]] = []
    capabilities = surface.capabilities if surface else frontdoor_capabilities()
    for capability in capabilities:
        binding = binding_registry.resolve(capability)
        if binding is None:
            logger.warning(
                "frontdoor surface names '%s', which resolves to no binding - skipping",
                capability,
            )
            continue
        if surface:
            decision = surface.decide(capability, binding)
        else:
            decision = evaluate_without_declaration(
                store=policy_store,
                tool_name=capability,
                caller_groups=identity.groups,
                request_classification=classification,
                equivalent_names=binding.all_names(),
            )
        if not decision.allowed:
            continue
        entry = policy_store.get_tool(capability)
        description = getattr(entry, "description", None) or (
            f"Zuno platform capability '{capability}', served by the "
            f"'{binding.backend}' backend through the Zuno MCP Gateway."
        )
        is_read_only = capability not in _NON_READONLY_CAPABILITIES
        tools.append(
            {
                "name": capability,
                "description": description,
                "inputSchema": _input_schema(binding),
                # ADR-0524 clause 4: every capability reachable here is a
                # read, except the deliberate exceptions in
                # _NON_READONLY_CAPABILITIES above. Lightspeed's
                # toolsApprovalConfig defaults to `tool_annotations`, so this
                # is what decides whether the console prompts the user
                # before a call.
                "annotations": {"readOnlyHint": is_read_only, "destructiveHint": False},
            }
        )
    return tools


async def dispatch(
    message: Dict[str, Any],
    *,
    policy_store: Any,
    binding_registry: Any,
    identity: Any,
    classification: str,
    invoke_tool: Callable[..., Any],
    surface: Optional[Surface] = None,
) -> Optional[Dict[str, Any]]:
    """Handle one JSON-RPC message. Returns None for notifications.

    `invoke_tool` is injected rather than imported so main.py keeps ownership of
    the full invoke path - span/telemetry, delegated-token resolution, the
    ADR-0340 self-scope check - instead of this module reimplementing a subset
    of it and drifting.
    """
    if not isinstance(message, dict):
        raise JsonRpcError(INVALID_REQUEST, "JSON-RPC message must be an object")
    if message.get("jsonrpc") != JSONRPC_VERSION:
        raise JsonRpcError(INVALID_REQUEST, "missing or unsupported 'jsonrpc' version")

    method = message.get("method")
    if not isinstance(method, str):
        raise JsonRpcError(INVALID_REQUEST, "missing 'method'")

    request_id = message.get("id")
    is_notification = "id" not in message

    # Notifications carry no id and MUST NOT be answered. `initialized` is the
    # one every MCP client sends right after `initialize`; answering it makes
    # strict clients drop the session.
    if is_notification:
        if method.startswith("notifications/"):
            return None
        logger.info("mcp frontdoor: ignoring non-notification message with no id: %s", method)
        return None

    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                # Only tools. This gateway exposes no prompts, resources or
                # sampling, and advertising them would invite calls that then
                # fail with METHOD_NOT_FOUND.
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "zuno-mcp-gateway", "version": "0.1.0"},
                "instructions": (
                    "Zuno MCP Gateway. Every tool call is authorized by the "
                    "ADR-0011 policy intersection using your validated identity; "
                    "tools/list already reflects what you may call."
                ),
            },
        )

    if method == "ping":
        return _result(request_id, {})

    if method == "tools/list":
        return _result(
            request_id,
            {
                "tools": list_tools(
                    policy_store=policy_store,
                    binding_registry=binding_registry,
                    identity=identity,
                    classification=classification,
                    surface=surface,
                )
            },
        )

    if method == "tools/call":
        params = message.get("params") or {}
        if not isinstance(params, dict):
            raise JsonRpcError(INVALID_PARAMS, "'params' must be an object")
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise JsonRpcError(INVALID_PARAMS, "'params.name' is required")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise JsonRpcError(INVALID_PARAMS, "'params.arguments' must be an object")

        # The exposed set is enforced HERE as well as in tools/list. Relying on
        # tools/list alone would make it advisory: a client is free to call a
        # name it was never advertised, and this endpoint's whole read-only
        # guarantee rests on that not working.
        if surface:
            binding = binding_registry.resolve(name)
            names = set(binding.all_names()) if binding else {name}
            exposed = bool(names & set(surface.capabilities))
        else:
            exposed = name in frontdoor_capabilities()
        if not exposed:
            logger.warning(
                "frontdoor refused '%s' - not exposed to this caller (caller=%s)",
                name,
                getattr(identity, "sub", "?"),
            )
            return _result(
                request_id,
                _tool_error(
                    f"'{name}' is not exposed through this MCP endpoint "
                    "(ADR-0524 front-door allowlist / ADR-0571 agent declaration)"
                ),
            )

        binding_for_names = binding_registry.resolve(name)
        arguments = normalise_arguments(
            binding_for_names.all_names() if binding_for_names else [name], arguments
        )
        if _is_search(binding_for_names.all_names() if binding_for_names else [name]) and not str(
            arguments.get("query", "")
        ).strip():
            # A search with no text cannot match anything: answer like an empty result instead of an error,
            # so the caller keeps its turn and decides what to do. The downstream tool is not called.
            return _result(request_id, _tool_ok("No pages found: the search text was empty."))
        try:
            payload = await invoke_tool(tool_name=name, arguments=arguments)
        except PermissionError as exc:
            # An authorization denial is a TOOL-level error, not a transport
            # one: the call was well-formed and the server understood it. See
            # JsonRpcError's docstring for why this distinction matters.
            return _result(request_id, _tool_error(f"denied: {exc}"))
        except LookupError as exc:
            return _result(request_id, _tool_error(f"unknown tool: {exc}"))
        except Exception as exc:  # noqa: BLE001 - surfaced to the client as a tool error
            # Argument NAMES only, never values: enough to see how a model called the tool.
            logger.warning(
                "mcp frontdoor: tool '%s' failed: %s (argument names: %s)", name, exc, sorted(arguments)
            )
            return _result(request_id, _tool_error(_short_error(exc)))
        return _result(request_id, _tool_ok(payload))

    raise JsonRpcError(METHOD_NOT_FOUND, f"unknown method '{method}'")


def error_response(request_id: Any, exc: JsonRpcError) -> Dict[str, Any]:
    return _error(request_id, exc.code, exc.message, exc.data)
