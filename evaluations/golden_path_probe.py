#!/usr/bin/env python3
"""The golden-path check of a live demonstration (ADR-0605 clause 1, WP-238).

One probe per demonstration moment, each a real call that must get a real answer:

  unifai-tekos         a Tekos turn in UnifAI, signed in as a persona through the UI route
  sovereignty          two ai-gateway calls from inside the gateway pod: Arkos (floor C3) must be routed to a local
                       model at C3, a Tekos control call stays at its header level
  delegation-approval  Arkos delegates to Tekos, the approval request appears and is rejected, so nothing runs
                       (evaluations/arkos/approval_proof.py reject), then the a2a-gateway's access line for the call to
                       Tekos (a rejected approval runs no tool, so there is no delegated mcp-gateway call to look for)
  open-webui           one answer through Open WebUI's API, signed in as a persona (OIDC through Keycloak)
  zuno-code            the same, with the declared code model `zuno-code` (ADR-0596, Codestral first)
  dify, kagent         one answer through the experience's own token proxy, from inside its pod (ADR-0601)
  openclaw             the per-persona assistants are Running; the answer itself is a manual checklist step
  lightspeed           the OLSConfig is Ready; the question itself is a manual checklist step
  world-model          roadmap until ADR-0604 ships a probe (WP-235)

Read-only with respect to the platform: the UnifAI sessions it creates are deleted, the approval request is rejected
and its session cancelled, and Open WebUI's chat-completions API stores no chat. It spends a few hundred tokens per
moment, the delegation moment much more (one Arkos turn).

Runs from a workstation where `oc` is logged in to the cluster. Credentials are read with `oc` and passed to the
probes through the environment or stdin, never printed:

    python3 evaluations/golden_path_probe.py
    python3 evaluations/golden_path_probe.py --only sovereignty,dify
    python3 evaluations/golden_path_probe.py --json

Exit code 0 when every required moment passes, 1 otherwise. `manual` and `roadmap` rows never fail the run.

Environment, all optional: OC_CONTEXT (an explicit `oc --context`), GOLDEN_PERSONA (UnifAI and Open WebUI persona,
default eval-consultant-01), GOLDEN_GATEWAY_PERSONA (the persona of the ai-gateway token, default consultant-01),
GOLDEN_VERIFY_TLS=1 (verify the routes' certificates), GOLDEN_SKIP (comma list of moments to skip).
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from typing import Callable, Dict, List, Optional

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE / "common"))

PASS, FAIL, MANUAL, ROADMAP, SKIPPED = "pass", "fail", "manual", "roadmap", "skipped"
_LOGIN_FORM_RE = re.compile(r'<form[^>]*id="kc-form-login"[^>]*action="([^"]+)"')
PROMPT = "In one short sentence, say what you can help me with."
VERIFY_TLS = os.getenv("GOLDEN_VERIFY_TLS", "0") == "1"


@dataclass
class Result:
    moment: str
    status: str
    detail: str
    required: bool = True
    seconds: float = 0.0


# -- cluster access ------------------------------------------------------------------------------------------------


def oc(*args: str, stdin: Optional[str] = None, timeout: float = 120) -> subprocess.CompletedProcess:
    cmd = ["oc"]
    if os.getenv("OC_CONTEXT"):
        cmd += ["--context", os.environ["OC_CONTEXT"]]
    return subprocess.run(cmd + list(args), input=stdin, capture_output=True, text=True, timeout=timeout)


def secret_value(namespace: str, name: str, key: str) -> str:
    jsonpath = "{.data." + key.replace(".", "\\.") + "}"
    out = oc("-n", namespace, "get", "secret", name, "-o", f"jsonpath={jsonpath}")
    if out.returncode != 0 or not out.stdout:
        raise RuntimeError(f"secret {namespace}/{name} key {key} not readable")
    return base64.b64decode(out.stdout).decode()


def cluster_domain() -> str:
    out = oc("get", "ingresses.config.openshift.io", "cluster", "-o", "jsonpath={.spec.domain}")
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError("cannot read the cluster's apps domain (is `oc` logged in?)")
    return out.stdout.strip()


def last_json_line(text: str) -> Dict:
    """The last line of `text` that parses as a JSON object, or {}."""
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return {}


class Context:
    def __init__(self) -> None:
        self.domain = cluster_domain()
        self.persona = os.getenv("GOLDEN_PERSONA", "eval-consultant-01")
        self.gateway_persona = os.getenv("GOLDEN_GATEWAY_PERSONA", "consultant-01")
        self.password = secret_value("zuno-ai-run", "acceptance-gate-credentials", "demo-persona-password")
        self._eval_secret = secret_value("zuno-ai-run", "acceptance-gate-credentials", "eval-client-secret")
        self.keycloak = f"https://keycloak.{self.domain}"
        self.unifai = f"https://unifai-ui-zuno-unifai.{self.domain}"
        self.open_webui = f"https://open-webui.{self.domain}"

    def gateway_token(self) -> str:
        """A zuno-evaluations token of the gateway persona, the token WP-209's live probe used."""
        import httpx

        r = httpx.post(
            f"{self.keycloak}/realms/zuno/protocol/openid-connect/token",
            data={"grant_type": "password", "client_id": "zuno-evaluations", "client_secret": self._eval_secret,
                  "username": self.gateway_persona, "password": self.password},
            timeout=30, verify=VERIFY_TLS,
        )
        if r.status_code != 200:
            raise RuntimeError(f"Keycloak refused the zuno-evaluations token: HTTP {r.status_code}")
        return r.json()["access_token"]

    def env(self) -> Dict[str, str]:
        """The environment the existing UnifAI harnesses read (approval_proof.py, unifai_target.py)."""
        e = dict(os.environ)
        e.update({"DEMO_PERSONA_PASSWORD": self.password, "UNIFAI_URL": self.unifai, "KEYCLOAK_URL": self.keycloak})
        return e


# -- probes --------------------------------------------------------------------------------------------------------


def probe_unifai_tekos(ctx: Context) -> Result:
    from unifai_target import UnifaiTarget

    t = UnifaiTarget(ctx.password, ui_url=ctx.unifai, agent="tekos", team_name="agent-tekos")
    try:
        run = t.run(ctx.persona, PROMPT, timeout=150)
    finally:
        deleted, failed = t.cleanup()
    routing = run.raw.get("routing") or {}
    where = f"{routing.get('provider')}/{routing.get('model')} at {routing.get('classification')}" if routing else "no routing"
    if run.status == 200 and run.reply.strip():
        return Result("unifai-tekos", PASS, f"answer in {run.seconds:.0f} s via {where}; {deleted} session(s) deleted")
    return Result("unifai-tekos", FAIL, f"HTTP {run.status}, empty answer={not run.reply.strip()}, "
                                        f"{str(run.raw.get('text') or run.raw.get('error') or '')[:160]}")


_GATEWAY_SNIPPET = r'''
import json, sys, uuid, httpx
token = sys.stdin.read().strip()
out = []
for level, agent, task in (("C1", "arkos", "draft-architecture-testimonial"), ("C1", "tekos", "answer-technical-question")):
    rid = "golden-" + uuid.uuid4().hex[:10]
    h = {"Authorization": "Bearer " + token, "X-Zuno-Request-Id": rid, "X-Zuno-Data-Classification": level,
         "X-Zuno-Agent": agent, "X-Zuno-Task": task}
    base = "http://127.0.0.1:8080/v1"
    try:
        r = httpx.post(base + "/chat/completions", headers=h, timeout=180,
                       json={"model": "auto", "messages": [{"role": "user", "content": "Say OK."}], "max_tokens": 16})
        d = httpx.get(base + "/routing-decisions/" + rid, headers={"Authorization": "Bearer " + token}, timeout=15)
        out.append({"agent": agent, "status": r.status_code, "routing": d.json() if d.status_code == 200 else None})
    except Exception as e:
        out.append({"agent": agent, "status": 0, "error": str(e)[:200]})
print(json.dumps({"calls": out}))
'''


def judge_sovereignty(calls: List[Dict]) -> Result:
    """Arkos (floor C3) must answer from a local model at C3; the Tekos control call must answer too."""
    by_agent = {c.get("agent"): c for c in calls}
    arkos, tekos = by_agent.get("arkos") or {}, by_agent.get("tekos") or {}
    r_ark = arkos.get("routing") or {}
    if arkos.get("status") != 200:
        return Result("sovereignty", FAIL, f"Arkos call: HTTP {arkos.get('status')} {arkos.get('error', '')}")
    if r_ark.get("kind") != "local" or r_ark.get("classification") != "C3":
        return Result("sovereignty", FAIL, f"Arkos was not kept local at C3: {r_ark or 'no routing decision'}")
    if tekos.get("status") != 200:
        return Result("sovereignty", FAIL, f"Tekos control call: HTTP {tekos.get('status')} {tekos.get('error', '')}")
    r_tek = tekos.get("routing") or {}
    return Result("sovereignty", PASS,
                  f"Arkos C1 raised to C3 -> {r_ark.get('provider')}/{r_ark.get('model')} (local); "
                  f"Tekos control at {r_tek.get('classification')} -> {r_tek.get('provider')}")


def probe_sovereignty(ctx: Context) -> Result:
    token = ctx.gateway_token()
    out = oc("-n", "zuno-ai-run", "exec", "-i", "deploy/ai-gateway", "-c", "ai-gateway", "--",
             "python3", "-c", _GATEWAY_SNIPPET, stdin=token, timeout=420)
    data = last_json_line(out.stdout)
    if not data:
        return Result("sovereignty", FAIL, f"no result from the gateway pod: {out.stderr.strip()[:200]}")
    return judge_sovereignty(data.get("calls") or [])


def judge_delegation(a2a_log: str, target: str = "tekos") -> Result:
    """After a rejected approval nothing runs, so no delegated tool call reaches the mcp-gateway. The delegation is
    proved by the a2a-gateway's access lines: the delegator's call to the target agent was served (200)."""
    from a2a_delegation_check import parse_a2a_access

    served = [status for agent, status in parse_a2a_access(a2a_log) if agent == target]
    ok = sum(1 for s in served if s == 200)
    if ok:
        return Result("delegation-approval", PASS, f"approval requested and rejected, nothing ran; the a2a-gateway "
                                                   f"served {ok} call(s) to {target}")
    return Result("delegation-approval", FAIL, f"approval rejected as asked, but the a2a-gateway served no call to "
                                               f"{target} in the window ({len(served)} line(s), statuses {sorted(set(served))})")


def probe_delegation_approval(ctx: Context) -> Result:
    sys.path.insert(0, str(REPO / "platform" / "testing"))
    from a2a_delegation_check import oc_logs

    started = time.monotonic()
    proof = subprocess.run([sys.executable, str(HERE / "arkos" / "approval_proof.py"), "reject"],
                           env=ctx.env(), capture_output=True, text=True, timeout=720)
    tail = " | ".join(l.strip() for l in (proof.stdout + proof.stderr).splitlines()[-3:] if l.strip())
    if proof.returncode != 0:
        return Result("delegation-approval", FAIL, f"approval_proof.py reject exit {proof.returncode}: {tail[:240]}")
    minutes = max(5, int((time.monotonic() - started) / 60) + 2)
    return judge_delegation(oc_logs("zuno-ai-run", "a2a-gateway", f"{minutes}m"))


def _keycloak_form_login(client, start_url: str, username: str, password: str):
    page = client.get(start_url)
    match = _LOGIN_FORM_RE.search(page.text)
    if not match:
        return None
    return client.post(html.unescape(match.group(1)), data={"username": username, "password": password, "credentialId": ""})


def _open_webui_session(ctx: Context):
    import httpx
    from unifai_target import login_name

    c = httpx.Client(follow_redirects=True, timeout=180, verify=VERIFY_TLS)
    landed = _keycloak_form_login(c, f"{ctx.open_webui}/oauth/oidc/login", login_name(ctx.persona), ctx.password)
    token = c.cookies.get("token")
    if landed is None or not token:
        c.close()
        raise RuntimeError("Open WebUI sign-in through Keycloak did not return a session token")
    return c, {"Authorization": f"Bearer {token}"}


def pick_model(ids: List[str], want: str) -> Optional[str]:
    """The Open WebUI model id for `want` ('code' -> the zuno-code model, else the default Zuno model)."""
    if want == "code":
        return next((i for i in ids if "zuno-code" in i), None)
    return next((i for i in ids if i == "auto" or i.endswith("auto")), next((i for i in ids if "zuno-code" not in i), None))


def _open_webui_answer(ctx: Context, moment: str, want: str) -> Result:
    c, auth = _open_webui_session(ctx)
    try:
        models = c.get(f"{ctx.open_webui}/api/models", headers=auth)
        ids = [m.get("id", "") for m in (models.json().get("data") or [])] if models.status_code == 200 else []
        model = pick_model(ids, want)
        if not model:
            return Result(moment, FAIL, f"no {'zuno-code' if want == 'code' else 'Zuno'} model in Open WebUI: {ids}")
        prompt = "Write a one-line Python function that adds two numbers." if want == "code" else PROMPT
        r = c.post(f"{ctx.open_webui}/api/chat/completions", headers=auth,
                   json={"model": model, "stream": False, "messages": [{"role": "user", "content": prompt}]})
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        if r.status_code == 200 and content.strip():
            return Result(moment, PASS, f"model {model} answered ({len(content)} chars, served by {body.get('model', '?')})")
        return Result(moment, FAIL, f"model {model}: HTTP {r.status_code} {str(body)[:200]}")
    finally:
        c.close()


def probe_open_webui(ctx: Context) -> Result:
    return _open_webui_answer(ctx, "open-webui", "chat")


def probe_zuno_code(ctx: Context) -> Result:
    return _open_webui_answer(ctx, "zuno-code", "code")


_PROXY_SNIPPET = r'''
import json, sys, urllib.request, urllib.error
body = json.dumps({"model": "auto", "stream": False, "max_tokens": 256,
                   "messages": [{"role": "user", "content": sys.argv[1]}]}).encode()
req = urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions", data=body,
                             headers={"Content-Type": "application/json", "Authorization": "Bearer placeholder"})
try:
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.load(r)
        m = (d.get("choices") or [{}])[0].get("message") or {}
        print(json.dumps({"status": r.status, "model": d.get("model"),
                          "chars": len((m.get("content") or "") + (m.get("reasoning_content") or ""))}))
except urllib.error.HTTPError as e:
    print(json.dumps({"status": e.code, "error": e.read()[:200].decode("utf-8", "replace")}))
except Exception as e:
    print(json.dumps({"status": 0, "error": str(e)[:200]}))
'''


def judge_proxy(moment: str, data: Dict, stderr: str = "") -> Result:
    if not data:
        return Result(moment, FAIL, f"no result from the token-proxy pod: {stderr.strip()[:200]}")
    if data.get("status") == 200 and data.get("chars", 0) > 0:
        return Result(moment, PASS, f"answer through the token proxy ({data['chars']} chars, model {data.get('model')})")
    return Result(moment, FAIL, f"token proxy: HTTP {data.get('status')} {data.get('error', 'empty answer')}")


def _proxy_answer(moment: str, namespace: str) -> Result:
    out = oc("-n", namespace, "exec", "deploy/zuno-token-proxy", "--", "python3", "-c", _PROXY_SNIPPET, PROMPT,
             timeout=240)
    return judge_proxy(moment, last_json_line(out.stdout), out.stderr)


def probe_dify(ctx: Context) -> Result:
    return _proxy_answer("dify", "zuno-dify")


def probe_kagent(ctx: Context) -> Result:
    return _proxy_answer("kagent", "zuno-kagent")


def probe_openclaw(ctx: Context) -> Result:
    out = oc("get", "pods", "-A", "-o", "json")
    pods = json.loads(out.stdout).get("items", []) if out.returncode == 0 else []
    claw = [p for p in pods if p["metadata"]["namespace"].startswith("zuno-claw-")]
    by_ns: Dict[str, List[str]] = {}
    for p in claw:
        ready = all(cs.get("ready") for cs in p.get("status", {}).get("containerStatuses", []) or [{}])
        by_ns.setdefault(p["metadata"]["namespace"], []).append("ok" if ready else p["metadata"]["name"])
    not_ready = {ns: [n for n in v if n != "ok"] for ns, v in by_ns.items() if any(n != "ok" for n in v)}
    if not by_ns:
        return Result("openclaw", FAIL, "no zuno-claw-* pod found", required=False)
    if not_ready:
        return Result("openclaw", FAIL, f"pods not ready: {not_ready}", required=False)
    return Result("openclaw", MANUAL, f"{len(by_ns)} persona namespace(s) all Ready ({', '.join(sorted(by_ns))}); "
                                      "ask the question on screen (checklist)", required=False)


def probe_lightspeed(ctx: Context) -> Result:
    out = oc("get", "olsconfig", "cluster", "-o", "json")
    if out.returncode != 0:
        return Result("lightspeed", FAIL, f"OLSConfig not readable: {out.stderr.strip()[:160]}", required=False)
    return judge_lightspeed(json.loads(out.stdout).get("status", {}).get("conditions", []) or [])


# The conditions the console chat needs. The others (agentic console plugin, alerts adapter) are features the
# demonstration does not show; they are reported, never failed on.
LIGHTSPEED_NEEDED = ("ApiReady", "ConsolePluginReady")


def judge_lightspeed(conds: List[Dict]) -> Result:
    state = {c.get("type"): c.get("status") for c in conds}
    missing = [t for t in LIGHTSPEED_NEEDED if state.get(t) != "True"]
    if missing:
        return Result("lightspeed", FAIL, f"OLSConfig not ready for the console chat: {missing}", required=False)
    other = sorted(t for t, v in state.items() if v != "True" and t not in LIGHTSPEED_NEEDED)
    note = f" (not used by the demo, not True: {', '.join(other)})" if other else ""
    return Result("lightspeed", MANUAL, f"API and console plugin Ready{note}; ask the question in the console "
                                        "(checklist)", required=False)


def probe_world_model(ctx: Context) -> Result:
    return Result("world-model", ROADMAP, "shown as roadmap until ADR-0604 ships a probe (WP-235)", required=False)


PROBES: Dict[str, Callable[[Context], Result]] = {
    "unifai-tekos": probe_unifai_tekos,
    "sovereignty": probe_sovereignty,
    "open-webui": probe_open_webui,
    "zuno-code": probe_zuno_code,
    "dify": probe_dify,
    "kagent": probe_kagent,
    "openclaw": probe_openclaw,
    "lightspeed": probe_lightspeed,
    "delegation-approval": probe_delegation_approval,
    "world-model": probe_world_model,
}
OPTIONAL = {"openclaw", "lightspeed", "world-model"}


def run_one(name: str, ctx: Context) -> Result:
    started = time.monotonic()
    try:
        res = PROBES[name](ctx)
    except Exception as exc:  # noqa: BLE001 - one broken moment never hides the others
        res = Result(name, FAIL, f"{type(exc).__name__}: {str(exc)[:200]}")
    res.required = name not in OPTIONAL
    res.seconds = round(time.monotonic() - started, 1)
    return res


def exit_code(results: List[Result]) -> int:
    return 1 if any(r.required and r.status == FAIL for r in results) else 0


def render(results: List[Result]) -> str:
    width = max(len(r.moment) for r in results)
    lines = [f"{r.status.upper():8} {r.moment:<{width}}  {r.seconds:6.1f}s  {r.detail}" for r in results]
    failed = [r.moment for r in results if r.required and r.status == FAIL]
    lines.append("RESULT: " + ("PASS" if not failed else f"FAIL ({', '.join(failed)})"))
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only", default="", help="comma list of moments (default: all)")
    ap.add_argument("--json", action="store_true", help="one JSON object per moment, then a summary")
    args = ap.parse_args(argv)
    names = [n for n in (args.only.split(",") if args.only else PROBES) if n]
    unknown = [n for n in names if n not in PROBES]
    if unknown:
        ap.error(f"unknown moment(s): {unknown}; known: {list(PROBES)}")
    skip = {s for s in os.getenv("GOLDEN_SKIP", "").split(",") if s}
    ctx = Context()
    results = []
    for n in names:
        if n in skip:
            results.append(Result(n, SKIPPED, "GOLDEN_SKIP", required=False))
            continue
        results.append(run_one(n, ctx))
        if not args.json:
            print(render(results[-1:]).splitlines()[0], flush=True)
    if args.json:
        for r in results:
            print(json.dumps(asdict(r)))
        print(json.dumps({"result": "PASS" if exit_code(results) == 0 else "FAIL"}))
    else:
        print(render(results).splitlines()[-1])
    return exit_code(results)


if __name__ == "__main__":
    sys.exit(main())
