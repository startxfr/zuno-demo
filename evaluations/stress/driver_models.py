"""Stress drivers of the `models` family (WP-305): calls to the ai-gateway through its in-cluster Service.

  ai-gateway-routing      one `zuno-code` call (the declared code model, Codestral first, ADR-0596) with the routing
                          decision read back: the golden-path moment `zuno-code` of ansible/demos/ai-gateway-routing
  ai-gateway-sovereignty  Arkos (floor C3) must be routed to a local model at C3 and a Tekos control call must answer
                          (the golden-path moment `sovereignty`, ansible/demos/ai-gateway-sovereignty)

Every call carries `X-Zuno-Quota-Class: stresstest` (only the zuno-stresstest client may pick a class) and a few tokens:
the stresstest class is a small, fail-closed budget, so a smoke run cannot drain the shared MaaS budget. The tokens each
answer costs are reported with ctx.add_tokens() for the runner's token cap.
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import golden_path_probe as gpp  # noqa: E402
from stress_runner import register, row  # noqa: E402

CODE_PROMPT = "Write a Python one-liner that reverses a string."
SAY_OK = "Say OK."


async def _chat(ctx, driver: str, i: int, step: str, token: str, model: str, prompt: str, agent: str, task: str,
                level: str = "C1", max_tokens: int = 32):
    """POST one chat completion; returns (response, request id, milliseconds)."""
    headers = {"Authorization": "Bearer " + token, "X-Zuno-Quota-Class": "stresstest", "X-Zuno-Data-Classification": level,
               "X-Zuno-Agent": agent, "X-Zuno-Task": task, **ctx.trace_headers(driver, i, step)}
    started = time.monotonic()
    r = await ctx.http.post(f"{ctx.ai_gateway}/v1/chat/completions", headers=headers, timeout=180, json={
        "model": model, "max_tokens": max_tokens, "stream": False, "messages": [{"role": "user", "content": prompt}]})
    return r, headers["X-Zuno-Request-Id"], (time.monotonic() - started) * 1000


def _answer(r) -> str:
    try:
        message = (r.json().get("choices") or [{}])[0].get("message") or {}
    except ValueError:
        return ""
    return (message.get("content") or "") + (message.get("reasoning_content") or "")


def _tokens(ctx, r) -> int:
    try:
        used = int((r.json().get("usage") or {}).get("total_tokens") or 0)
    except (ValueError, TypeError, AttributeError):
        used = 0
    ctx.add_tokens(used)
    return used


async def _routing(ctx, token: str, request_id: str):
    """The routing decision of a call (best effort: None when the gateway keeps none)."""
    r = await ctx.http.get(f"{ctx.ai_gateway}/v1/routing-decisions/{request_id}",
                           headers={"Authorization": "Bearer " + token}, timeout=15)
    return r.json() if r.status_code == 200 else None


@register("ai-gateway-routing", family="models",
          description="one zuno-code call through the ai-gateway, routing decision read back (golden-path moment `zuno-code`)",
          needs=("ai-gateway", "a code model (Codestral or a local fallback)"))
async def ai_gateway_routing(ctx, i):
    token = await ctx.token()
    r, rid, ms = await _chat(ctx, "ai-gateway-routing", i, "code", token, "zuno-code", CODE_PROMPT, "open-webui", "code")
    if r.status_code != 200:
        return [row("ai-gateway-routing", "functional", "zuno-code", "models", False,
                    f"status={r.status_code} {r.text[:160]}", ms)]
    used = _tokens(ctx, r)
    decision = await _routing(ctx, token, rid) or {}
    answered = bool(_answer(r).strip())
    return [row("ai-gateway-routing", "functional", "zuno-code", "models", answered,
                f"status=200 provider={decision.get('provider', '?')} model={decision.get('model', '?')} tokens={used}"
                + ("" if answered else " empty answer"), ms)]


@register("ai-gateway-sovereignty", family="models",
          description="Arkos kept local at C3 and a Tekos control call answered (golden-path moment `sovereignty`)",
          needs=("ai-gateway", "a local model"))
async def ai_gateway_sovereignty(ctx, i):
    token = await ctx.token()
    calls, spent = [], 0.0
    for agent, task in (("arkos", "draft-architecture-testimonial"), ("tekos", "answer-technical-question")):
        r, rid, ms = await _chat(ctx, "ai-gateway-sovereignty", i, agent, token, "auto", SAY_OK, agent, task, max_tokens=16)
        spent += ms
        _tokens(ctx, r)
        calls.append({"agent": agent, "status": r.status_code, "routing": await _routing(ctx, token, rid) if r.status_code == 200 else None,
                      "error": "" if r.status_code == 200 else r.text[:160]})
    verdict = gpp.judge_sovereignty(calls)
    worst = max(c["status"] for c in calls)
    return [row("ai-gateway-sovereignty", "functional", "sovereignty", "models", verdict.status == gpp.PASS,
                f"status={worst} {verdict.detail}", spent)]
