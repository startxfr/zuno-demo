"""Stress drivers that replay a network path from outside the cluster's own services (WP-308, ADR-0624).

  blender-3d              the Blender add-on's path: a device sign-in of the public client `blender` as a stress persona
                          (no human: evaluations/blender/device_login.py), then /v1/models and one chat completion on
                          https://ai-gateway.<domain> (the workstation entry). Skipped when the entry is off (404).
  claude-code-sovereign   Claude Code's path: a device sign-in of the public client `claude-code`, then one Anthropic
                          /v1/messages call on https://praxis.<domain> (the Praxis workstation entry).
  quotas                  burns the persona's `stresstest` token budget through the ai-gateway until it answers 429
                          (ADR-0555's proof). Mutating: it spends a persona's budget, so it runs only when the profile
                          sets allow_mutating, and only as a persona of the stress pool.

The two public Routes are not in the zuno-ai-run egress allow-list today (WP-308 adds them): until then the row carries
the connection error. Praxis injects its own MaaS credential, so claude-code-sovereign spends the Praxis budget; the
profiles keep it at one request at a time behind the budget guard.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
import time

_EVALUATIONS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_EVALUATIONS))
sys.path.insert(0, str(_EVALUATIONS / "blender"))

import golden_path_probe as gpp  # noqa: E402
import stress_runner as sr  # noqa: E402
from stress_runner import register, row  # noqa: E402

TOKEN_TTL = 4 * 60
_DEVICE_TOKENS = {}  # (persona, client) -> (access token, expiry)


def _domain(ctx) -> str:
    return ctx.env.get("CLUSTER_BASE_DOMAIN", "apps.invalid")


def device_access_token(issuer: str, persona: str, password: str, client_id: str) -> str:
    """The access token of a device sign-in of `persona` on `client_id`, cached for four minutes. Blocking."""
    from device_login import device_token

    return sr.cached_signin(_DEVICE_TOKENS, (persona, client_id), TOKEN_TTL,
                            lambda: device_token(issuer, persona, password, timeout=90, client_id=client_id)["access_token"])


async def _device(ctx, client_id: str) -> str:
    issuer = ctx.keycloak + "/realms/zuno"
    return await asyncio.to_thread(device_access_token, issuer, ctx.persona, ctx.env.get("DEMO_PERSONA_PASSWORD", ""), client_id)


def _answer(body: dict) -> str:
    message = (body.get("choices") or [{}])[0].get("message") or {}
    return (message.get("content") or "") + (message.get("reasoning_content") or "")


@register("blender-3d", family="experiences",
          description="the Blender add-on's path: device sign-in, /v1/models and one chat on the workstation entry (golden-path moment `blender`)",
          needs=("the ai-gateway workstation entry (workstationEntry.enabled)", "egress to ai-gateway.<domain>"))
async def blender_3d(ctx, i):
    started = time.monotonic()
    base = (ctx.env.get("AI_GATEWAY_PUBLIC_URL") or "https://ai-gateway." + _domain(ctx)).rstrip("/")
    token = await _device(ctx, "blender")
    auth = {"Authorization": "Bearer " + token, **ctx.trace_headers("blender-3d", i)}
    models = await ctx.http.get(f"{base}/v1/models", headers=auth, timeout=60)
    if models.status_code == 404:
        return [row("blender-3d", "functional", "blender", "experiences", True,
                    "status=404 skipped: the ai-gateway workstation entry is off, nothing to replay", (time.monotonic() - started) * 1000)]
    r = await ctx.http.post(f"{base}/v1/chat/completions", headers=auth, timeout=180, json={
        "model": "auto", "max_tokens": 32, "stream": False, "messages": [{"role": "user", "content": "Reply with the single word OK."}]})
    ms = (time.monotonic() - started) * 1000
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    ctx.add_tokens((body.get("usage") or {}).get("total_tokens") or 0)
    passed = models.status_code == 200 and r.status_code == 200 and bool(_answer(body).strip())
    worst = max(models.status_code, r.status_code)  # the guard reads the first status=NNN of the detail
    return [row("blender-3d", "functional", "blender", "experiences", passed,
                f"status={worst} models={models.status_code} chat={r.status_code}" + ("" if passed else f" {r.text[:120]}"), ms)]


@register("claude-code-sovereign", family="experiences",
          description="Claude Code's path: device sign-in, one /v1/messages call on the Praxis workstation entry",
          needs=("the Praxis workstation entry (praxisWorkstationEntry)", "egress to praxis.<domain>"))
async def claude_code_sovereign(ctx, i):
    started = time.monotonic()
    base = (ctx.env.get("PRAXIS_PUBLIC_URL") or "https://praxis." + _domain(ctx)).rstrip("/")
    token = await _device(ctx, "claude-code")
    r = await ctx.http.post(f"{base}/v1/messages", timeout=180, headers={
        "Authorization": "Bearer " + token, "anthropic-version": "2023-06-01", **ctx.trace_headers("claude-code-sovereign", i)},
        json={"model": ctx.env.get("CLAUDE_CODE_MODEL", "qwen3.6-27b-instruct"), "max_tokens": 32,
              "messages": [{"role": "user", "content": "Reply with the single word OK."}]})
    ms = (time.monotonic() - started) * 1000
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    text = "".join(block.get("text", "") for block in body.get("content") or [] if isinstance(block, dict))
    usage = body.get("usage") or {}
    ctx.add_tokens((usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0))
    passed = r.status_code == 200 and bool(text.strip())
    return [row("claude-code-sovereign", "functional", "claude-code", "experiences", passed,
                f"status={r.status_code} " + (f"{len(text)} chars" if passed else r.text[:160]), ms)]


def judge_burst(statuses, limit: int):
    """(passed, detail) of a burst until the first 429: the proof is the 429; a 502 everywhere means the models are down."""
    if 429 in statuses:
        return True, f"status=429 after {statuses.index(429) + 1} short call(s)"
    if statuses and all(s >= 500 for s in statuses):
        return False, f"status={statuses[-1]} every call failed: the models are down, the budget could not be spent"
    return False, f"status={statuses[-1] if statuses else 0} no 429 within {len(statuses)} call(s) (limit {limit})"


@register("quotas", family="quota", mutating=True,
          description="spend the persona's stresstest token budget until the ai-gateway answers 429 (ADR-0555's proof)",
          needs=("ai-gateway", "a stress persona dedicated to this proof"))
async def quotas(ctx, i):
    started = time.monotonic()
    token = await ctx.token()
    limit = int(ctx.env.get("QUOTA_BURST_MAX_CALLS", "30"))
    headers = {"Authorization": "Bearer " + token, "X-Zuno-Quota-Class": "stresstest", "X-Zuno-Data-Classification": "C1",
               **ctx.trace_headers("quotas", i)}
    statuses = []
    for _ in range(limit):  # sequential on purpose: the ledger checks before it consumes, a parallel burst only blurs the crossing
        r = await ctx.http.post(f"{ctx.ai_gateway}/v1/chat/completions", headers=headers, timeout=120, json={
            "model": "auto", "max_tokens": 120, "stream": False,
            "messages": [{"role": "user", "content": "Write a short paragraph (at least 80 words) about Kubernetes namespaces."}]})
        statuses.append(r.status_code)
        if r.status_code == 200:
            try:
                ctx.add_tokens((r.json().get("usage") or {}).get("total_tokens") or 0)
            except ValueError:
                pass
        if r.status_code == 429:
            break
    passed, detail = judge_burst(statuses, limit)
    return [row("quotas", "functional", "quota-429", "quota", passed, detail, (time.monotonic() - started) * 1000)]
