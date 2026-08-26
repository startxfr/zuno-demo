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
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("mcp_gateway.frontdoor")

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
    agents: Any,
    binding_registry: Any,
    identity: Any,
    agent_name: str,
    task_name: str,
    classification: str,
) -> List[Dict[str, Any]]:
    """Every capability this caller is actually authorized for, right now.

    Computed by running the SAME `evaluate()` the invoke path runs, once per
    known capability. That is a few hundred in-memory dict lookups, not a
    network call - cheap enough to do per request, and it means the advertised
    surface can never drift from the enforced one.
    """
    from app.policy import evaluate

    tools: List[Dict[str, Any]] = []
    for capability in binding_registry.capabilities():
        binding = binding_registry.resolve(capability)
        if binding is None:
            continue
        decision = evaluate(
            store=policy_store,
            agents=agents,
            tool_name=capability,
            agent_name=agent_name,
            task_name=task_name,
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
        tools.append(
            {
                "name": capability,
                "description": description,
                "inputSchema": _input_schema(binding),
                # ADR-0524 clause 4: every capability reachable here is a read.
                # Lightspeed's toolsApprovalConfig defaults to
                # `tool_annotations`, so this is what decides whether the
                # console prompts the user before a call.
                "annotations": {"readOnlyHint": True, "destructiveHint": False},
            }
        )
    return tools


async def dispatch(
    message: Dict[str, Any],
    *,
    policy_store: Any,
    agents: Any,
    binding_registry: Any,
    identity: Any,
    agent_name: str,
    task_name: str,
    classification: str,
    invoke_tool: Callable[..., Any],
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
                    agents=agents,
                    binding_registry=binding_registry,
                    identity=identity,
                    agent_name=agent_name,
                    task_name=task_name,
                    classification=classification,
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
            logger.warning("mcp frontdoor: tool '%s' failed: %s", name, exc)
            return _result(request_id, _tool_error(str(exc)))
        return _result(request_id, _tool_ok(payload))

    raise JsonRpcError(METHOD_NOT_FOUND, f"unknown method '{method}'")


def error_response(request_id: Any, exc: JsonRpcError) -> Dict[str, Any]:
    return _error(request_id, exc.code, exc.message, exc.data)
