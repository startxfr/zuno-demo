# Run inside the Dify api pod by `make d2 configure dify` (ADR-0599 decision 3). Idempotent: creates the single local
# administrator, installs the OpenAI-compatible provider plugin, registers the models behind the token proxy and the
# governed MCP gateway as a tool. The input is one JSON object on stdin (the password never reaches argv or a log):
# {email, password, pkg, models: [{name, mode, context}], proxy, mcp_name}
import base64
import json
import sys
import time

import requests

IN = json.load(sys.stdin)
BASE = "http://localhost:5001/console/api"
PROVIDER = "langgenius/openai_api_compatible/openai_api_compatible"
S = requests.Session()


def call(method, path, ok=(200, 201), **kw):
    h = kw.pop("headers", {})
    # The cookies are Secure and the pod talks plain http: send the same values explicitly.
    h["Cookie"] = "; ".join(f"{c.name}={c.value}" for c in S.cookies)
    for name, header, prefix in (("csrf_token", "X-CSRF-Token", ""), ("access_token", "Authorization", "Bearer ")):
        for c in S.cookies:
            if c.name in (name, "__Host-" + name):
                h[header] = prefix + c.value
    r = S.request(method, BASE + path, headers=h, timeout=120, **kw)
    if r.status_code not in ok:
        print(f"FAIL {method} {path} -> {r.status_code} {r.text[:300]}")
        sys.exit(1)
    return r.json() if r.content else {}


def b64(v):
    return base64.b64encode(v.encode()).decode()


# 1. administrator
if call("GET", "/setup").get("step") != "finished":
    call("POST", "/setup", json={"email": IN["email"], "name": "Zuno administrator", "password": IN["password"]})
    print("setup: created")
else:
    print("setup: already finished")
call("POST", "/login", json={"email": IN["email"], "password": b64(IN["password"]), "remember_me": True})
print("login: ok")

# 2. plugin
inst = call("GET", "/workspaces/current/plugin/list?page=1&page_size=100")
if any(p.get("plugin_id") == "langgenius/openai_api_compatible" for p in inst.get("plugins", [])):
    print("plugin: already installed")
else:
    with open(IN["pkg"], "rb") as f:
        up = call("POST", "/workspaces/current/plugin/upload/pkg", files={"pkg": ("oac.difypkg", f)})
    uid = up["unique_identifier"]
    r = call("POST", "/workspaces/current/plugin/install/pkg", json={"plugin_unique_identifiers": [uid]})
    if not r.get("all_installed"):
        for _ in range(60):
            t = call("GET", f"/workspaces/current/plugin/tasks/{r['task_id']}")["task"]
            st = [p["status"] for p in t["plugins"]]
            if all(s == "success" for s in st):
                break
            if any(s == "failed" for s in st):
                print("FAIL plugin install", json.dumps(t)[:500])
                sys.exit(1)
            time.sleep(5)
        else:
            print("FAIL plugin install timeout")
            sys.exit(1)
    print("plugin: installed", uid)

# 3. models
have = call("GET", f"/workspaces/current/model-providers/{PROVIDER}/models").get("data", [])
names = {m.get("model") for m in have}
for m in IN["models"]:
    if m["name"] in names:
        print("model:", m["name"], "already registered")
        continue
    call("POST", f"/workspaces/current/model-providers/{PROVIDER}/models/credentials", json={
        "model": m["name"], "model_type": "llm",
        "credentials": {
            "mode": m["mode"], "context_size": str(m["context"]), "max_tokens_to_sample": "4096",
            "display_name": m["name"], "api_key": "dummy-dropped-by-the-token-proxy",
            "endpoint_url": IN["proxy"] + "/v1", "endpoint_model_name": m["name"],
            "function_calling_type": "no_call", "stream_function_calling": "not_supported",
            "vision_support": "no_support", "structured_output_support": "not_supported",
        },
    })
    print("model:", m["name"], "registered")

# 4. MCP tool
tools = call("GET", "/workspaces/current/tools/mcp")
if any(t.get("name") == IN["mcp_name"] for t in (tools if isinstance(tools, list) else tools.get("data", []))):
    print("mcp: already registered")
else:
    call("POST", "/workspaces/current/tool-provider/mcp", json={
        "server_url": IN["proxy"] + "/mcp", "name": IN["mcp_name"], "icon": "🛠️", "icon_type": "emoji",
        "icon_background": "#FFEAD5", "server_identifier": "zuno-mcp-gateway", "headers": {},
        "timeout": 30, "sse_read_timeout": 300,
    })
    print("mcp: registered")
