"""Client for the MCP Gateway (components/mcp-gateway), used by the
`tool_call` graph node. Forwards the caller's own Bearer JWT so the
gateway's ADR-0011 policy check runs against the real end user's identity
(ADR-0013 propagation), not a service credential.
"""

from __future__ import annotations

import os
from typing import Any, Dict

import httpx

MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "http://mcp-gateway.zuno-ai-run.svc:8080")
MCP_TIMEOUT_SECONDS = float(os.getenv("MCP_TIMEOUT_SECONDS", "20"))


class McpClientError(Exception):
    pass


async def invoke_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    bearer_token: str,
    agent_name: str,
    task_name: str,
    data_classification: str = "C1",
) -> Dict[str, Any]:
    """agent_name/task_name (ADR-0036) declare which OKF-defined agent/task
    is making this call, so the gateway can enforce the agent_declaration
    and task_rights factors of the ADR-0011 intersection - required, not
    optional, since the gateway fails closed on a missing declaration.
    """
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "X-Zuno-Data-Classification": data_classification,
        "X-Zuno-Agent": agent_name,
        "X-Zuno-Task": task_name,
    }
    try:
        async with httpx.AsyncClient(timeout=MCP_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{MCP_GATEWAY_URL}/v1/tools/{tool_name}/invoke",
                json=arguments,
                headers=headers,
            )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise McpClientError(str(exc)) from exc
    return resp.json()
