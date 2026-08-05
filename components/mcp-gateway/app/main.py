"""Zuno MCP Gateway (ADR-0010, ADR-0011).

Central entry point for every MCP tool call in the platform: validates the
caller's Keycloak JWT, computes the policy-intersection authorization
decision, and proxies to the right downstream MCP server or demo-mode
handler. See README.md for the exact HTTP API contract.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Dict

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.agent_declarations import AgentDeclarationStore
from app.auth import CallerIdentity, validate_token
from app.downstream import DownstreamError
from app.downstream import invoke as invoke_downstream
from app.policy import PolicyStore, evaluate
from app.telemetry import init_telemetry, tool_invoke_span

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("mcp_gateway")

init_telemetry("mcp-gateway")  # ADR-0029: traces/metrics to the shared OTel Collector

app = FastAPI(
    title="Zuno MCP Gateway",
    version="0.1.0",
    description=(
        "Central MCP Gateway (ADR-0010): authorizes and proxies every MCP "
        "tool call behind a single ADR-0011 policy-intersection decision."
    ),
)

policy_store = PolicyStore()
agent_declarations = AgentDeclarationStore()  # ADR-0036/0038: agents/<name>/agent.okf.md bundles

KNOWN_TOOLS = {
    "search_confluence",
    "list_drive_files",
    "read_gmail",
    "get_customer",
    "list_open_opportunities",
    "get_quote",
    "web_search",
    "send_technical_report_email",
}


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    if policy_store.loaded and agent_declarations.loaded:
        return JSONResponse({"status": "ready"})
    reasons = [
        r
        for r in (policy_store.load_error, agent_declarations.load_error)
        if r
    ]
    return JSONResponse(
        {"status": "not-ready", "reason": "; ".join(reasons) or "policy not loaded"},
        status_code=503,
    )


@app.post("/admin/reload-policy")
async def reload_policy() -> Dict[str, Any]:
    """Operational escape hatch: re-reads tool-policy.yaml,
    classification.yaml and the agents/ OKF bundles from disk without a pod
    restart, for the case where Track B's policy files or an agent
    definition land after this pod already started.
    """
    policy_store.reload()
    agent_declarations.reload()
    return {
        "loaded": policy_store.loaded and agent_declarations.loaded,
        "error": policy_store.load_error or agent_declarations.load_error,
        "tools": policy_store.known_tools(),
    }


@app.post("/v1/tools/{tool_name}/invoke")
async def invoke_tool(
    tool_name: str,
    request: Request,
    identity: CallerIdentity = Depends(validate_token),
    x_zuno_data_classification: str = Header(default="C1", alias="X-Zuno-Data-Classification"),
    x_zuno_agent: str = Header(default="", alias="X-Zuno-Agent"),
    x_zuno_task: str = Header(default="", alias="X-Zuno-Task"),
) -> Dict[str, Any]:
    request_id = str(uuid.uuid4())
    started = time.monotonic()
    classification = x_zuno_data_classification.upper()

    with tool_invoke_span(tool_name, classification) as call:
        if tool_name not in KNOWN_TOOLS:
            call.outcome = "unknown_tool"
            raise HTTPException(status_code=404, detail=f"unknown tool '{tool_name}'")

        raw_body = await request.body()
        if raw_body:
            try:
                arguments = json.loads(raw_body)
            except json.JSONDecodeError as exc:
                call.outcome = "bad_request"
                raise HTTPException(status_code=400, detail=f"request body is not valid JSON: {exc}") from exc
        else:
            arguments = {}
        if not isinstance(arguments, dict):
            call.outcome = "bad_request"
            raise HTTPException(status_code=400, detail="request body must be a JSON object of tool arguments")

        decision = evaluate(
            store=policy_store,
            agents=agent_declarations,
            tool_name=tool_name,
            agent_name=x_zuno_agent,
            task_name=x_zuno_task,
            caller_groups=identity.groups,
            request_classification=classification,
        )
        call.mcp_server = decision.mcp_server
        call.reason = decision.reason

        logger.info(
            "tool=%s agent=%s task=%s caller=%s groups=%s classification=%s allowed=%s reason=%s request_id=%s",
            tool_name,
            x_zuno_agent,
            x_zuno_task,
            identity.sub,
            identity.groups,
            x_zuno_data_classification,
            decision.allowed,
            decision.reason,
            request_id,
        )

        if not decision.allowed:
            call.outcome = "denied"
            raise HTTPException(status_code=403, detail=decision.reason)

        try:
            result = await invoke_downstream(tool_name, arguments, identity.sub, identity.token)
        except DownstreamError as exc:
            call.outcome = "downstream_error"
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

        call.outcome = "allowed"
        duration_ms = (time.monotonic() - started) * 1000
        return {
            "tool": tool_name,
            "request_id": request_id,
            "mcp_server": decision.mcp_server,
            "duration_ms": round(duration_ms, 1),
            # ADR-0035: tells the caller (Agent Runtime) whether this
            # result may be processed by an external SaaS model or must
            # stay local, independent of the classification the caller
            # itself declared - the Agent Runtime uses this to set
            # X-Zuno-Local-Only on its own downstream model call.
            "external_model_policy": {"allow_context": decision.allow_external_context},
            "result": result,
        }
