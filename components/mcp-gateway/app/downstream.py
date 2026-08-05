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

from app.handlers import confluence, drive, email_report, gmail, web_search

logger = logging.getLogger("mcp_gateway.downstream")

# ASSUMPTION (document + reconcile once components/mcp-servers/sales-db is
# finalized by its owning track): the sales-db MCP server is reachable as
# an HTTP+SSE MCP endpoint inside the cluster at this address, exposing
# standard MCP `tools/call` semantics over a JSON-RPC-style POST. If the
# real server instead speaks MCP-over-stdio via a sidecar, only
# `_invoke_sales_db` below needs to change.
SALES_DB_MCP_URL = os.getenv("SALES_DB_MCP_URL", "http://sales-db-mcp.zuno-ai.svc:8000")
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
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    headers = {"Authorization": f"Bearer {bearer_token}", "X-Zuno-Gateway-Token": MCP_GATEWAY_WORKLOAD_TOKEN}
    try:
        async with httpx.AsyncClient(timeout=DOWNSTREAM_TIMEOUT_SECONDS) as client:
            resp = await client.post(f"{SALES_DB_MCP_URL}/mcp", json=payload, headers=headers)
        resp.raise_for_status()
        body = resp.json()
    except httpx.HTTPError as exc:
        logger.error("sales-db MCP server call failed for tool '%s': %s", tool_name, exc)
        raise DownstreamError(502, f"sales-db MCP server unreachable or errored: {exc}") from exc

    if isinstance(body, dict) and "error" in body:
        raise DownstreamError(502, f"sales-db MCP server returned an error: {body['error']}")
    return body.get("result", body) if isinstance(body, dict) else {"raw": body}
