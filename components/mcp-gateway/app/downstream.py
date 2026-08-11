"""Routes an authorized tool invocation to the correct downstream MCP
server or demo-mode handler.

Routing is keyed by tool name (fixed by the platform-wide tool contract)
rather than by the ``mcp_server`` string in ``tool-policy.yaml``: the
policy file's ``mcp_server`` field is authored by Track B and its exact
values aren't guaranteed to match a naming scheme this module can key off
safely, whereas the eight tool names themselves are a stable contract
shared across tracks. The resolved ``mcp_server`` label from the policy
decision is still threaded through for observability/logging.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

import httpx
import httpx2  # the mcp SDK's own httpx fork/client type, required by streamable_http_client
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError

from app.handlers import confluence, drive, email_report, gmail, web_search

logger = logging.getLogger("mcp_gateway.downstream")

# ADR-0043: sales-db is a real, standards-compliant MCP server (streamable-
# HTTP transport, mounted at /mcp - see components/mcp-servers/sales-db/
# server.py) reached here via the official `mcp` SDK's ClientSession, not
# the hand-rolled JSON-RPC-shaped POST this file used before. Only
# `_invoke_sales_db` below needed to change - `invoke()`'s own signature
# and every caller (app/main.py) are unaffected, exactly as this module's
# docstring anticipated before the migration.
SALES_DB_MCP_URL = os.getenv("SALES_DB_MCP_URL", "http://sales-db-mcp.zuno-ai-run.svc:8000")
SALES_DB_MCP_ENDPOINT = f"{SALES_DB_MCP_URL}/mcp"
DOWNSTREAM_TIMEOUT_SECONDS = float(os.getenv("DOWNSTREAM_TIMEOUT_SECONDS", "20"))

# ADR-0037: a shared secret (vault-generated,
# ansible/roles/vault/tasks/configure.yml,
# secret/zuno/mcp/gateway-workload-token) proving this call actually came
# from the MCP Gateway, not merely from a pod that happens to be
# network-adjacent - NetworkPolicy is the first layer (gitops/charts/
# mcp-sales-db's NetworkPolicy restricts ingress to this service's pods
# specifically); this is the "validate the gateway workload identity in
# addition to relying on network location" second layer this ADR requires
# for sensitive MCP servers. Not enforced as a hard startup requirement
# here (unlike sales-db's own validation) so this gateway still starts and
# serves every other tool if the secret hasn't landed yet - the sales-db
# call itself degrades to a clear 502 from the missing/rejected header.
MCP_GATEWAY_WORKLOAD_TOKEN = os.getenv("MCP_GATEWAY_WORKLOAD_TOKEN", "")

SALES_DB_TOOLS = {"get_customer", "list_open_opportunities", "get_quote"}

DEMO_MODE_HANDLERS = {
    "search_confluence": confluence.handle,
    "list_drive_files": drive.handle,
    "read_gmail": gmail.handle,
    "web_search": web_search.handle,
    "send_technical_report_email": email_report.handle,
}


class DownstreamError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


async def invoke(
    tool_name: str, arguments: Dict[str, Any], caller_sub: str, bearer_token: str
) -> Dict[str, Any]:
    if tool_name in SALES_DB_TOOLS:
        return await _invoke_sales_db(tool_name, arguments, bearer_token)

    handler = DEMO_MODE_HANDLERS.get(tool_name)
    if handler is None:
        raise DownstreamError(502, f"no downstream handler registered for tool '{tool_name}'")
    return await handler(arguments, caller_sub)


async def _invoke_sales_db(
    tool_name: str, arguments: Dict[str, Any], bearer_token: str
) -> Dict[str, Any]:
    # Authorization is still forwarded for audit/observability even though
    # sales-db doesn't itself re-validate it (the gateway's ADR-0011 policy
    # intersection already happened - see components/mcp-servers/sales-db/
    # server.py's module docstring); X-Zuno-Gateway-Token is the one that's
    # actually enforced (ADR-0037).
    headers = {"Authorization": f"Bearer {bearer_token}", "X-Zuno-Gateway-Token": MCP_GATEWAY_WORKLOAD_TOKEN}
    try:
        http_client = httpx2.AsyncClient(timeout=DOWNSTREAM_TIMEOUT_SECONDS, headers=headers)
        async with streamable_http_client(SALES_DB_MCP_ENDPOINT, http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
    except MCPError as exc:
        logger.error("sales-db MCP server returned a protocol-level error for tool '%s': %s", tool_name, exc)
        raise DownstreamError(502, f"sales-db MCP server returned an error: {exc}") from exc
    except (httpx.HTTPError, OSError) as exc:
        logger.error("sales-db MCP server call failed for tool '%s': %s", tool_name, exc)
        raise DownstreamError(502, f"sales-db MCP server unreachable or errored: {exc}") from exc

    if result.is_error:
        detail = "; ".join(block.text for block in result.content if hasattr(block, "text"))
        raise DownstreamError(502, f"sales-db MCP server returned a tool error: {detail}")

    if result.structured_content is not None:
        # Verified against the real SDK (mcp==2.0.0): a tool whose return
        # type annotation is a plain dict (every sales-db tool) gets its
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
