"""Stress drivers of the experience clients (WP-308, ADR-0624): the network path each UI or proxy takes to the models.

  open-webui, open-webui-zuno-code, open-webui-zuno-wesh
                       one answer through Open WebUI's API, signed in through Keycloak as a stress persona, with the
                       default Zuno model, the declared code model `zuno-code` and the declared `zuno-wesh`
                       (golden-path moments open-webui, zuno-code, zuno-wesh)
  dify, kagent         one answer through the experience's own token proxy (ADR-0601), which swaps in its client's token
                       (golden-path moments dify, kagent)

They need two network openings that are not in the platform today (WP-308 lists them): the zuno-ai-run egress firewall
must admit the open-webui Route, and each token proxy's NetworkPolicy must admit the stress Job's pods. Until then the
driver reports the connection error as its row, which is the honest answer. These drivers spend the shared experience
clients' budgets (they are the real user paths), so the profiles keep them at one request at a time.

OpenClaw and Lightspeed are NOT replayed from a Job: OpenClaw's path is the operator's egress proxy inside each persona's
pod (nothing to call from outside), and Lightspeed needs an OpenShift token the OLS app server accepts.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
import time

_EVALUATIONS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_EVALUATIONS))

import golden_path_probe as gpp  # noqa: E402
from stress_runner import register, row  # noqa: E402

CODE_PROMPT = "Write a one-line Python function that adds two numbers."
TOKEN_TTL = 15 * 60
_TOKENS = {}  # persona -> (Open WebUI session token, expiry): one Keycloak sign-in serves many calls


def _open_webui_url(ctx) -> str:
    return (ctx.env.get("OPEN_WEBUI_URL") or "https://open-webui." + ctx.env.get("CLUSTER_BASE_DOMAIN", "apps.invalid")).rstrip("/")


def owui_login(base: str, username: str, password: str) -> str:
    """The Open WebUI session token of `username` (OIDC through Keycloak's form, as the golden probe does). Blocking."""
    import httpx

    with httpx.Client(follow_redirects=True, timeout=180) as client:
        landed = gpp._keycloak_form_login(client, f"{base}/oauth/oidc/login", username, password)
        token = client.cookies.get("token")
    if landed is None or not token:
        raise RuntimeError("Open WebUI sign-in through Keycloak did not return a session token")
    return token


def owui_chat(base: str, token: str, want: str, prompt: str):
    """(status, model, content, served_by, ids): the models list, then one non-streaming chat. Blocking."""
    import httpx

    auth = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=180) as client:
        listed = client.get(f"{base}/api/models", headers=auth)
        ids = [m.get("id", "") for m in (listed.json().get("data") or [])] if listed.status_code == 200 else []
        model = gpp.pick_model(ids, want)
        if not model:
            return listed.status_code, "", "", "", ids
        r = client.post(f"{base}/api/chat/completions", headers=auth,
                        json={"model": model, "stream": False, "messages": [{"role": "user", "content": prompt}]})
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        return r.status_code, model, content, str(body.get("model", "?")), ids


def judge_owui(driver: str, want: str, status: int, model: str, content: str, served_by: str, ids):
    if not model:
        label = {"code": "zuno-code", "wesh": "zuno-wesh"}.get(want, "Zuno")
        return False, f"status={status} no {label} model in Open WebUI: {ids}"
    if status == 200 and content.strip():
        return True, f"status=200 model {model} answered ({len(content)} chars, served by {served_by})"
    return False, f"status={status} model {model} gave no answer"


def _register_open_webui(driver_id: str, want: str, prompt: str, moment: str):
    @register(driver_id, family="experiences",
              description=f"one {want} answer through Open WebUI's API as a stress persona (golden-path moment `{moment}`)",
              needs=("open-webui", "egress to the open-webui Route"))
    async def run(ctx, i):
        started = time.monotonic()
        persona = ctx.persona
        cached = _TOKENS.get(persona)
        if not cached or cached[1] < time.time():
            token = await asyncio.to_thread(owui_login, _open_webui_url(ctx), persona, ctx.env.get("DEMO_PERSONA_PASSWORD", ""))
            _TOKENS[persona] = (token, time.time() + TOKEN_TTL)
        token = _TOKENS[persona][0]
        status, model, content, served_by, ids = await asyncio.to_thread(owui_chat, _open_webui_url(ctx), token, want, prompt)
        if status in (401, 403):
            _TOKENS.pop(persona, None)  # the next iteration signs in again
        passed, detail = judge_owui(driver_id, want, status, model, content, served_by, ids)
        return [row(driver_id, "functional", moment, "experiences", passed, detail, (time.monotonic() - started) * 1000)]

    return run


open_webui = _register_open_webui("open-webui", "chat", gpp.PROMPT, "open-webui")
open_webui_code = _register_open_webui("open-webui-zuno-code", "code", CODE_PROMPT, "zuno-code")
open_webui_wesh = _register_open_webui("open-webui-zuno-wesh", "wesh", gpp.PROMPT, "zuno-wesh")


def _register_proxy(driver_id: str, namespace: str, env_name: str):
    @register(driver_id, family="experiences",
              description=f"one answer through the {namespace} token proxy (golden-path moment `{driver_id}`)",
              needs=(f"zuno-token-proxy in {namespace}", "its NetworkPolicy admits the stress Job"))
    async def run(ctx, i):
        url = (ctx.env.get(env_name) or f"http://zuno-token-proxy.{namespace}.svc:8080").rstrip("/")
        started = time.monotonic()
        # The proxy swaps in its own Keycloak client token: the bearer is a placeholder, as in the golden probe.
        key = ctx.env.get(env_name + "_KEY", "placeholder")  # the proxy's inbound key when inboundAuth is on, else any string
        r = await ctx.http.post(f"{url}/v1/chat/completions", headers={"Authorization": f"Bearer {key}", **ctx.trace_headers(driver_id, i)},
                                timeout=180, json={"model": "auto", "stream": False, "max_tokens": 64,
                                                   "messages": [{"role": "user", "content": gpp.PROMPT}]})
        ms = (time.monotonic() - started) * 1000
        try:
            body = r.json()
        except ValueError:
            body = {}
        message = (body.get("choices") or [{}])[0].get("message") or {}
        chars = len((message.get("content") or "") + (message.get("reasoning_content") or ""))
        ctx.add_tokens((body.get("usage") or {}).get("total_tokens") or 0)
        verdict = gpp.judge_proxy(driver_id, {"status": r.status_code, "chars": chars, "model": body.get("model"),
                                              "error": r.text[:160] if r.status_code != 200 else ""})
        return [row(driver_id, "functional", driver_id, "experiences", verdict.status == gpp.PASS, f"status={r.status_code} {verdict.detail}", ms)]

    return run


dify = _register_proxy("dify", "zuno-dify", "DIFY_PROXY_URL")
kagent = _register_proxy("kagent", "zuno-kagent", "KAGENT_PROXY_URL")
