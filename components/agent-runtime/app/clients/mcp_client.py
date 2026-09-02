"""Client for the MCP Gateway (components/mcp-gateway), used by the
`tool_call` graph node. Forwards the caller's own Bearer JWT so the
gateway's ADR-0011 policy check runs against the real end user's identity
(ADR-0013 propagation), not a service credential.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "http://mcp-gateway.zuno-ai-run.svc:8080")
# 20s was too short for a real capability against a real large dataset -
# live-cluster-confirmed 2026-08-23: git.repository.list against the real
# "openshift" GitHub org (500+ repos, server-side paginated) timed out here
# even though git-forge-mcp would have eventually succeeded.
MCP_TIMEOUT_SECONDS = float(os.getenv("MCP_TIMEOUT_SECONDS", "40"))


class McpClientError(Exception):
    """status_code is None for a transport-level failure (timeout,
    connection refused, DNS) and set to the response status for an
    HTTP-level failure (e.g. 403 from the gateway's policy denial) - callers
    that need to distinguish "denied" from "unreachable" (ADR-0512's binding
    step) read this instead of parsing the message string.
    """

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


async def invoke_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    bearer_token: str,
    agent_name: str,
    task_name: str,
    data_classification: str = "C1",
    run_id: Optional[str] = None,
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
    if run_id:
        # ADR-0543: lets mcp-gateway tag its tool_invoke span with the
        # calling chat turn's run_id, so a run's resource-consumption
        # dashboard can find every tool call it made.
        headers["X-Zuno-Run-Id"] = run_id
    try:
        async with httpx.AsyncClient(timeout=MCP_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{MCP_GATEWAY_URL}/v1/tools/{tool_name}/invoke",
                json=arguments,
                headers=headers,
            )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        raise McpClientError(str(exc), status_code=status_code) from exc
    return resp.json()
