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

from app.auth import CallerIdentity, validate_token
from app.downstream import DownstreamError
from app.downstream import invoke as invoke_downstream
from app.policy import PolicyStore, evaluate

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("mcp_gateway")

app = FastAPI(
    title="Zuno MCP Gateway",
    version="0.1.0",
    description=(
        "Central MCP Gateway (ADR-0010): authorizes and proxies every MCP "
        "tool call behind a single ADR-0011 policy-intersection decision."
    ),
)

policy_store = PolicyStore()

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
    if policy_store.loaded:
        return JSONResponse({"status": "ready"})
    return JSONResponse(
        {"status": "not-ready", "reason": policy_store.load_error or "policy not loaded"},
        status_code=503,
    )


@app.post("/admin/reload-policy")
async def reload_policy() -> Dict[str, Any]:
    """Operational escape hatch: re-reads tool-policy.yaml and
    classification.yaml from disk without a pod restart, for the case where
    Track B's policy files land after this pod already started.
    """
    policy_store.reload()
    return {
        "loaded": policy_store.loaded,
        "error": policy_store.load_error,
        "tools": policy_store.known_tools(),
    }


@app.post("/v1/tools/{tool_name}/invoke")
async def invoke_tool(
    tool_name: str,
    request: Request,
    identity: CallerIdentity = Depends(validate_token),
    x_zuno_data_classification: str = Header(default="C1", alias="X-Zuno-Data-Classification"),
) -> Dict[str, Any]:
    request_id = str(uuid.uuid4())
    started = time.monotonic()

    if tool_name not in KNOWN_TOOLS:
        raise HTTPException(status_code=404, detail=f"unknown tool '{tool_name}'")

    raw_body = await request.body()
    if raw_body:
        try:
            arguments = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"request body is not valid JSON: {exc}") from exc
    else:
        arguments = {}
    if not isinstance(arguments, dict):
        raise HTTPException(status_code=400, detail="request body must be a JSON object of tool arguments")

    decision = evaluate(
        store=policy_store,
        tool_name=tool_name,
        caller_groups=identity.groups,
        request_classification=x_zuno_data_classification.upper(),
    )

    logger.info(
        "tool=%s caller=%s groups=%s classification=%s allowed=%s reason=%s request_id=%s",
        tool_name,
        identity.sub,
        identity.groups,
        x_zuno_data_classification,
        decision.allowed,
        decision.reason,
        request_id,
    )

    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.reason)

    try:
        result = await invoke_downstream(tool_name, arguments, identity.sub, identity.token)
    except DownstreamError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    duration_ms = (time.monotonic() - started) * 1000
    return {
        "tool": tool_name,
        "request_id": request_id,
        "mcp_server": decision.mcp_server,
        "duration_ms": round(duration_ms, 1),
        "result": result,
    }
