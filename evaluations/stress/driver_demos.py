"""Stress drivers for demos that had no probe of their own (WP-310 batch 2, ADR-0624).

  maas-portal-api-keys   the gate of the MaaS public entry: `GET <maas>/<namespace>/<model>/v1/models` WITHOUT a key must be
                         refused (401/403), the demo's 2:15 step. A 200 means the gate is open: a failing row.
  identity-personas      the identity every other driver rides: the stress persona's password-grant token, its claims read
                         (issuer, client, subject name, expiry) and the groups it carries counted, no signature check here
                         (the gateways verify it; this row says what Keycloak issued).
  multi-gateway          the same short question through the Zuno ai-gateway (persona token) and through Praxis (device
                         sign-in of the public client `claude-code`), one row each, so a difference between the two doors shows.

Not here, on purpose (see docs/roadmap/work-packages/wp-310-*.md): `genai-playground` and `evaluation-trustyai-evalhub` are driven
by their web UIs and have no HTTP contract a Job can replay without a browser; `agents-alt-gateway` waits for Phase 58 (the
kagent agent on Praxis); `delegation-approval` and `unifai-live-rag` change a persona's state and need a dedicated persona and the
owner's go; the unsigned-image refusal needs an admission request the read-only role must not make.
"""
from __future__ import annotations

import asyncio
import base64
import json
import pathlib
import sys
import time

_STRESS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_STRESS))

import driver_network as net  # noqa: E402
from stress_runner import register, row  # noqa: E402

REFUSED = (401, 403)
QUESTION = "Reply with the single word OK."


def maas_url(env: dict) -> str:
    """The MaaS public entry of the demo: https://maas.<domain>/<namespace>/<model> (ansible/demos/maas-portal-api-keys/demo.yml)."""
    return (env.get("MAAS_URL") or f"https://maas.{env.get('CLUSTER_BASE_DOMAIN', 'apps.invalid')}/zuno-ai-run/gpt-oss-20b").rstrip("/")


def judge_unauthenticated(status: int) -> tuple:
    """(passed, detail) of a call WITHOUT a key on the MaaS entry: refused is the proof, a 200 is an open gate."""
    if status in REFUSED:
        return True, f"status={status} refused without an API key"
    if status == 200:
        return False, "status=200 the MaaS entry answered WITHOUT an API key: the gate is open"
    return False, f"status={status} neither refused (401/403) nor answered: the entry is not behaving as a gate"


@register("maas-portal-api-keys", family="experiences",
          description="the MaaS entry refuses a /v1/models call without an API key (the demo's 2:15 step)",
          needs=("egress to maas.<domain>",))
async def maas_portal_api_keys(ctx, i):
    started = time.monotonic()
    r = await ctx.http.get(maas_url(ctx.env) + "/v1/models", timeout=30, headers=ctx.trace_headers("maas-portal-api-keys", i))
    passed, detail = judge_unauthenticated(r.status_code)
    return [row("maas-portal-api-keys", "functional", "no-key-refused", "experiences", passed, detail, (time.monotonic() - started) * 1000)]


def token_claims(token: str) -> dict:
    """The payload of a JWT, unverified (the signature is the gateways' job). {} when it is not a JWT."""
    try:
        part = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    except (IndexError, ValueError):
        return {}


def judge_identity(claims: dict, persona: str, client_id: str, now: float) -> tuple:
    """(passed, detail): the token is the persona's, for the stress client, from the zuno realm, and not expired."""
    problems = []
    if not claims:
        return False, "the access token is not a JWT"
    if str(claims.get("preferred_username", "")) != persona:
        problems.append(f"preferred_username={claims.get('preferred_username')!r}")
    if claims.get("azp") != client_id:
        problems.append(f"azp={claims.get('azp')!r}")
    if not str(claims.get("iss", "")).rstrip("/").endswith("/realms/zuno"):
        problems.append(f"iss={claims.get('iss')!r}")
    if float(claims.get("exp", 0)) <= now:
        problems.append("expired")
    groups = claims.get("groups") or []
    detail = f"{persona} azp={claims.get('azp')} groups={len(groups) if isinstance(groups, list) else 0}"
    return (not problems), (detail if not problems else f"{detail}: {', '.join(problems)}")


@register("identity-personas", family="experiences",
          description="the stress persona's Keycloak token: issuer, client, subject and expiry (the identity every driver rides)",
          needs=("keycloak", "a persona pool"))
async def identity_personas(ctx, i):
    started = time.monotonic()
    token = await ctx.token()
    passed, detail = judge_identity(token_claims(token), ctx.persona, ctx.env.get("EVAL_CLIENT_ID", "zuno-stresstest"), time.time())
    return [row("identity-personas", "functional", "persona-token", "experiences", passed, detail, (time.monotonic() - started) * 1000)]


def _answer_of(body: dict) -> str:
    message = (body.get("choices") or [{}])[0].get("message") or {}
    return (message.get("content") or "") + (message.get("reasoning_content") or "")


@register("multi-gateway", family="experiences",
          description="one short question through the Zuno ai-gateway and through Praxis: one row per door",
          needs=("ai-gateway", "the Praxis workstation entry (praxisWorkstationEntry)", "egress to praxis.<domain>"))
async def multi_gateway(ctx, i):
    rows = []
    started = time.monotonic()
    token = await ctx.token()
    r = await ctx.http.post(f"{ctx.ai_gateway}/v1/chat/completions", timeout=180, headers={
        "Authorization": "Bearer " + token, "X-Zuno-Data-Classification": "C1", **ctx.trace_headers("multi-gateway", i)},
        json={"model": "auto", "max_tokens": 64, "stream": False, "messages": [{"role": "user", "content": QUESTION}]})
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    ctx.add_tokens((body.get("usage") or {}).get("total_tokens") or 0)
    answered = r.status_code == 200 and bool(_answer_of(body).strip())
    rows.append(row("multi-gateway", "functional", "zuno-ai-gateway", "experiences", answered,
                    f"status={r.status_code}" + ("" if answered else f" {r.text[:120]}"), (time.monotonic() - started) * 1000))

    started = time.monotonic()
    base = (ctx.env.get("PRAXIS_PUBLIC_URL") or "https://praxis." + net._domain(ctx)).rstrip("/")
    device = await net._device(ctx, "claude-code")
    p = await ctx.http.post(f"{base}/v1/messages", timeout=180, headers={
        "Authorization": "Bearer " + device, "anthropic-version": "2023-06-01", **ctx.trace_headers("multi-gateway", i)},
        json={"model": ctx.env.get("CLAUDE_CODE_MODEL", "qwen3.6-27b-instruct"), "max_tokens": 128,
              "messages": [{"role": "user", "content": QUESTION}]})
    pbody = p.json() if p.headers.get("content-type", "").startswith("application/json") else {}
    usage = pbody.get("usage") or {}
    ctx.add_tokens((usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0))
    passed, detail = net.judge_messages(p.status_code, pbody, p.text)
    rows.append(row("multi-gateway", "functional", "praxis", "experiences", passed, detail, (time.monotonic() - started) * 1000))
    return rows
