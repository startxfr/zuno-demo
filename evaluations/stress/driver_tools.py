"""Stress drivers of the `tools` family (WP-305): the governed tool path through the mcp-gateway REST endpoint.

  mcp-tools-by-group   one `search_confluence` call as the gateway persona for Tekos's task, answered by the confluence
                       MCP server with at least one page (the golden-path moment `tools`, ansible/demos/mcp-tools-by-group)

Runs in an in-cluster Job: service URL, a zuno-stresstest token, no `oc`. The verdict is the golden-path judge.
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import golden_path_probe as gpp  # noqa: E402
from stress_runner import register, row  # noqa: E402


def to_row(driver: str, res, http_status: int, ms: float):
    """A golden-path Result as a Day2Result row; `status=NNN` is what the budget guard reads."""
    return row(driver, "functional", res.moment, "tools", res.status == gpp.PASS, f"status={http_status} {res.detail}", ms)


@register("mcp-tools-by-group", family="tools",
          description="search_confluence through the mcp-gateway REST path (golden-path moment `tools`)",
          needs=("mcp-gateway", "mcp-confluence"))
async def mcp_tools_by_group(ctx, i):
    token = await ctx.token()
    headers = {"Authorization": "Bearer " + token, "X-Zuno-Data-Classification": "C2", "X-Zuno-Agent": "tekos",
               "X-Zuno-Task": "answer-technical-question", **ctx.trace_headers("mcp-tools-by-group", i)}
    started = time.monotonic()
    r = await ctx.http.post(f"{ctx.mcp_gateway}/v1/tools/search_confluence/invoke", headers=headers,
                            json={"query": "onboarding"}, timeout=60)
    ms = (time.monotonic() - started) * 1000
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    result = body.get("result") or {}
    verdict = gpp.judge_tool({
        "status": r.status_code, "server": body.get("mcp_server"), "ms": body.get("duration_ms"),
        "results": len(result.get("results") or []) if isinstance(result, dict) else 0,
        "error": "" if r.status_code == 200 else r.text[:160]})
    return [to_row("mcp-tools-by-group", verdict, r.status_code, ms)]
