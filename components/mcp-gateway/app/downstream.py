"""Routes an authorized tool invocation to the physical backend its
ADR-0116 binding names.

Routing is no longer keyed by hard-coded tool-name sets: main.py resolves
the caller's tool name (canonical capability ID or migration alias) through
app/bindings.py's registry BEFORE calling ``invoke()``, and this module
dispatches purely on the resolved ``Binding`` - its transport, endpoint and
the backend's own ``provider_tool`` name. An unresolved binding fails
closed here with the same ``DownstreamError`` contract callers already
depend on; no name ever falls through to a default backend.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx
import httpx2  # the mcp SDK's own httpx fork/client type, required by streamable_http_client
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError

from app.bindings import Binding
from app.handlers import diagram_gen, drive, email_report, gmail, image_gen, web_search

logger = logging.getLogger("mcp_gateway.downstream")

# Matches app/clients/mcp_client.py's MCP_TIMEOUT_SECONDS on the
# agent-runtime side (also bumped from 20s) - live-cluster-confirmed
# 2026-08-23: git.repository.list against the real "openshift" GitHub org
# (500+ repos, server-side paginated) still timed out here even after that
# other hop was widened, since this is a second, independent timeout on
# the gateway's own call to the downstream MCP server.
DOWNSTREAM_TIMEOUT_SECONDS = float(os.getenv("DOWNSTREAM_TIMEOUT_SECONDS", "40"))

# ADR-0037: a shared secret (vault-generated,
# ansible/roles/vault/tasks/configure.yml,
# secret/zuno/mcp/gateway-workload-token) proving this call actually came
# from the MCP Gateway, not merely from a pod that happens to be
# network-adjacent - NetworkPolicy is the first layer (gitops/charts/
# mcp-each downstream server's NetworkPolicy restricts ingress to this service's pods
# specifically); this is the "validate the gateway workload identity in
# addition to relying on network location" second layer this ADR requires
# for sensitive MCP servers. Not enforced as a hard startup requirement
# here (unlike the downstream server's own validation) so this gateway still starts and
# serves every other tool if the secret hasn't landed yet - the MCP call
# itself degrades to a clear 502 from the missing/rejected header.
MCP_GATEWAY_WORKLOAD_TOKEN = os.getenv("MCP_GATEWAY_WORKLOAD_TOKEN", "")

# The in-process demo-mode backends themselves (ADR-0116: this is the
# physical-backend catalog the `in-process` transport dispatches into, keyed
# by the binding's `handler` field - not a per-tool routing set; which tool
# reaches which handler is the registry's decision, not this module's).
IN_PROCESS_HANDLERS = {
    "drive": drive.handle,
    # ADR-0326 (WP-31): Arkos's delegated Drive/Docs write - same module,
    # two more single-purpose handler names (see app/handlers/drive.py's
    # own docstring for why one name maps to one function here rather than
    # branching inside a shared handle()).
    "drive_create": drive.handle_create,
    "drive_update": drive.handle_update,
    "gmail": gmail.handle,
    "web_search": web_search.handle,
    "email_report": email_report.handle,
    # ADR-0415: not a demo-mode stub like the rest of this dict - calls
    # the real, already-deployed components/ai-gateway in-cluster.
    "image_gen": image_gen.handle,
    # ADR-0516: same posture - calls the real, in-cluster diagram-render
    # service (never an external SaaS call, unlike image_gen above).
    "diagram_gen": diagram_gen.handle,
}


class DownstreamError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


async def invoke(
    binding: Optional[Binding],
    tool_name: str,
    arguments: Dict[str, Any],
    caller_sub: str,
    bearer_token: str,
    delegated_token: Optional[str] = None,
) -> Dict[str, Any]:
    if binding is None:
        # Fail closed (ADR-0116): deterministic error, no backend contacted.
        raise DownstreamError(502, f"no backend binding registered for tool '{tool_name}'")

    if binding.transport == "streamable-http":
        return await _invoke_streamable_http(binding, arguments, bearer_token)

    if binding.transport == "in-process":
        handler = IN_PROCESS_HANDLERS.get(binding.handler or "")
        if handler is None:
            raise DownstreamError(
                502,
                f"binding '{binding.capability}' names unknown in-process handler "
                f"'{binding.handler}'",
            )
        # ADR-0208: delegated_token is None for every non-delegated-user
        # binding (app/main.py only resolves one when auth_mode requires
        # it) - handlers that don't need it simply ignore the kwarg.
        # ADR-0415: bearer_token is forwarded the same way, for the one
        # handler (image_gen) that makes a real in-cluster call and needs
        # the caller's own identity to reach it - every other handler
        # ignores it, same as delegated_token above.
        return await handler(arguments, caller_sub, delegated_token=delegated_token, bearer_token=bearer_token)

    raise DownstreamError(
        502, f"binding '{binding.capability}' has unsupported transport '{binding.transport}'"
    )


async def _invoke_streamable_http(
    binding: Binding, arguments: Dict[str, Any], bearer_token: str
) -> Dict[str, Any]:
    # ADR-0043: real, standards-compliant MCP servers (streamable-HTTP
    # transport, e.g. components/mcp-servers/salesforce/server.py mounted at
    # /mcp) reached via the official `mcp` SDK's ClientSession. The endpoint
    # comes from the binding's registry entry (environment-resolved at call
    # time), and the tool actually called is the binding's `provider_tool` -
    # the backend's own name, which callers using canonical capability IDs
    # never see.
    #
    # Authorization is still forwarded for audit/observability even though
    # downstream servers don't themselves re-validate it (the gateway's
    # ADR-0011 policy intersection already happened);
    # X-Zuno-Gateway-Token is the one that's actually enforced (ADR-0037).
    endpoint = binding.endpoint_url()
    headers = {"Authorization": f"Bearer {bearer_token}", "X-Zuno-Gateway-Token": MCP_GATEWAY_WORKLOAD_TOKEN}
    try:
        http_client = httpx2.AsyncClient(timeout=DOWNSTREAM_TIMEOUT_SECONDS, headers=headers)
        async with streamable_http_client(endpoint, http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(binding.provider_tool, arguments)
    except MCPError as exc:
        logger.error(
            "%s MCP server returned a protocol-level error for tool '%s': %s",
            binding.backend, binding.provider_tool, exc,
        )
        raise DownstreamError(502, f"{binding.backend} MCP server returned an error: {exc}") from exc
    except (httpx.HTTPError, OSError) as exc:
        logger.error(
            "%s MCP server call failed for tool '%s': %s", binding.backend, binding.provider_tool, exc
        )
        raise DownstreamError(502, f"{binding.backend} MCP server unreachable or errored: {exc}") from exc

    if result.is_error:
        detail = "; ".join(block.text for block in result.content if hasattr(block, "text"))
        raise DownstreamError(502, f"{binding.backend} MCP server returned a tool error: {detail}")

    if result.structured_content is not None:
        # Verified against the real SDK (mcp==2.0.0): a tool whose return
        # type annotation is a plain dict (every confluence tool) gets its
        # structured content wrapped as {"result": <value>} - MCP requires
        # structured content to have an object-typed top-level schema, and
        # a bare dict return has none, so the SDK wraps it. Unwrap that
        # single-key envelope rather than leaking SDK plumbing into the
        # gateway's own response shape, which callers expect to match the
        # pre-migration `{"customer": ..., "contacts": ...}` shape exactly.
        if set(result.structured_content.keys()) == {"result"}:
            return result.structured_content["result"]
        return result.structured_content
    text_blocks = [block.text for block in result.content if hasattr(block, "text")]
    return {"raw": "\n".join(text_blocks)}
