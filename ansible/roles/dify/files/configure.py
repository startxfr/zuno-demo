# Run inside the Dify api pod by `make d2 configure dify` (ADR-0599 decision 3). Idempotent: creates the single local
# administrator, installs the OpenAI-compatible provider plugin, registers the models behind the token proxy and the
# governed MCP gateway as a tool. The input is one JSON object on stdin (the password never reaches argv or a log):
# {email, password, pkg, models: [{name, mode, context}], proxy, mcp_name, proxy_key (WP-225 lot C, may be empty)}
import base64
import json
import sys
import time

import requests

IN = json.load(sys.stdin)
BASE = "http://localhost:5001/console/api"
PROVIDER = "langgenius/openai_api_compatible/openai_api_compatible"
S = requests.Session()


def call(method, path, ok=(200, 201, 204), **kw):
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

# 3. models. Both models answer tool calls through the token proxy and the ai-gateway (checked live 2026-11-05), so
# they are registered with function_calling_type tool_call: the Agent app needs the model's "tool-call" feature.
have = call("GET", f"/workspaces/current/model-providers/{PROVIDER}/models").get("data", [])
registered = {m.get("model"): m for m in have}


def credentials(m):
    return {
        "model": m["name"], "model_type": "llm",
        "credentials": {
            "mode": m["mode"], "context_size": str(m["context"]), "max_tokens_to_sample": "4096",
            # WP-225 lot C: the token proxy's inbound key when it asks for one; the proxy drops it either way.
            "display_name": m["name"], "api_key": IN.get("proxy_key") or "dummy-dropped-by-the-token-proxy",
            "endpoint_url": IN["proxy"] + "/v1", "endpoint_model_name": m["name"],
            "function_calling_type": "tool_call", "stream_function_calling": "supported",
            "vision_support": "no_support", "structured_output_support": "not_supported",
        },
    }


for m in IN["models"]:
    cur = registered.get(m["name"])
    if cur and any("tool-call" in f for f in (cur.get("features") or [])):
        print("model:", m["name"], "already registered with tool calls")
        continue
    if cur:
        call("DELETE", f"/workspaces/current/model-providers/{PROVIDER}/models", params={"model": m["name"], "model_type": "llm"}, json={"model": m["name"], "model_type": "llm"})
        print("model:", m["name"], "re-registered to enable tool calls")
    call("POST", f"/workspaces/current/model-providers/{PROVIDER}/models/credentials", json=credentials(m))
    print("model:", m["name"], "registered")

# 4. MCP tool
tools = call("GET", "/workspaces/current/tools/mcp")
if any(t.get("name") == IN["mcp_name"] for t in (tools if isinstance(tools, list) else tools.get("data", []))):
    print("mcp: already registered")
else:
    call("POST", "/workspaces/current/tool-provider/mcp", json={
        "server_url": IN["proxy"] + "/mcp", "name": IN["mcp_name"], "icon": "🛠️", "icon_type": "emoji",
        "icon_background": "#FFEAD5", "server_identifier": "zuno-mcp-gateway",
        "headers": {"Authorization": "Bearer " + IN["proxy_key"]} if IN.get("proxy_key") else {},
        "timeout": 30, "sse_read_timeout": 300,
    })
    print("mcp: registered")

# The registration leaves the server unauthorised with no tool ("Serveur Non Configuré" in the console):
# authorise it, then fetch its tools. The id the console API wants is the database uuid, which only
# /tool-providers returns (the /tools/mcp list gives the server_identifier).
providers = call("GET", "/workspaces/current/tool-providers")
providers = providers if isinstance(providers, list) else providers.get("data", [])
mcp = next((p for p in providers if p.get("type") == "mcp" and p.get("name") == IN["mcp_name"]), None)
if mcp is None:
    print("FAIL mcp provider not found in /tool-providers")
    sys.exit(1)
if not mcp.get("is_team_authorization"):
    call("POST", "/workspaces/current/tool-provider/mcp/auth", json={"provider_id": mcp["id"]})
    print("mcp: authorised")
listed = call("GET", f"/workspaces/current/tool-provider/mcp/tools/{mcp['id']}")
if not listed.get("tools"):
    call("GET", f"/workspaces/current/tool-provider/mcp/update/{mcp['id']}")
    listed = call("GET", f"/workspaces/current/tool-provider/mcp/tools/{mcp['id']}")
    print("mcp: tools fetched")
print("mcp: tools", [t["name"] for t in listed.get("tools", [])])

# 5. External Knowledge (WP-205): the adapter as an External Knowledge API, and one knowledge base on it.
# Optional input: knowledge = {endpoint, api_key, api_name, kb_name, kb_id, top_k, score_threshold}.
K = IN.get("knowledge")
if K:
    apis = call("GET", "/datasets/external-knowledge-api?page=1&limit=100")
    found = [a for a in apis.get("data", []) if a.get("name") == K["api_name"]]
    if found:
        api_id = found[0]["id"]
        print("knowledge api: already registered")
    else:
        # Dify probes POST {endpoint}/retrieval with an empty id and query; the adapter answers 200 {"records": []}.
        api_id = call("POST", "/datasets/external-knowledge-api", json={
            "name": K["api_name"], "settings": {"endpoint": K["endpoint"], "api_key": K["api_key"]},
        })["id"]
        print("knowledge api: registered")
    datasets = call("GET", "/datasets?page=1&limit=100&include_all=true")
    if any(d.get("name") == K["kb_name"] for d in datasets.get("data", [])):
        print("knowledge base: already registered")
    else:
        call("POST", "/datasets/external", json={
            "external_knowledge_api_id": api_id, "external_knowledge_id": K["kb_id"], "name": K["kb_name"],
            "description": "Group-filtered, classification-marked technical documentation (Confluence, Red Hat product docs).",
            "external_retrieval_model": {"top_k": K["top_k"], "score_threshold": K["score_threshold"],
                                          "score_threshold_enabled": False},
        })
        print("knowledge base: registered")


# 6. example applications (WP-208): the DSL files of files/apps/, imported once by name. The MCP tools are named in
# the DSL by the server identifier (what the agent and workflow runtimes resolve), so nothing in them is specific to
# this instance; Dify drops the plain dataset ids of an imported DSL, so the external knowledge base is attached
# through the draft APIs after the import.
import glob
import os

import yaml

KB_NAME = (IN.get("knowledge") or {}).get("kb_name", "Zuno technical documentation")
dataset = next((d for d in call("GET", "/datasets?page=1&limit=100&include_all=true").get("data", [])
                if d.get("name") == KB_NAME), None)
if dataset is None:
    print("FAIL external knowledge base not found: run the adapter step first")
    sys.exit(1)

apps = call("GET", "/apps?page=1&limit=100").get("data", [])
by_name = {a["name"]: a for a in apps}


def attach_dataset(app_id, mode):
    """Attach the external knowledge base; True when something changed (idempotent)."""
    if mode == "agent-chat":
        detail = call("GET", f"/apps/{app_id}")
        cfg = detail["model_config"]
        listed = cfg.get("dataset_configs", {}).get("datasets", {}).get("datasets", [])
        if any(d.get("dataset", {}).get("id") == dataset["id"] for d in listed):
            return False
        cfg.setdefault("dataset_configs", {})["datasets"] = {"datasets": [{"dataset": {"enabled": True, "id": dataset["id"]}}]}
        call("POST", f"/apps/{app_id}/model-config", json=cfg)
        return True
    if mode == "advanced-chat":
        draft = call("GET", f"/apps/{app_id}/workflows/draft")
        nodes = [n for n in draft["graph"]["nodes"] if n["data"].get("type") == "knowledge-retrieval"]
        if all(dataset["id"] in n["data"].get("dataset_ids", []) for n in nodes):
            return False
        for n in nodes:
            n["data"]["dataset_ids"] = [dataset["id"]]
        call("POST", f"/apps/{app_id}/workflows/draft", json={"graph": draft["graph"], "features": draft.get("features", {}), "hash": draft.get("hash")})
        return True
    return False


for path in sorted(glob.glob(os.path.join(IN["apps_dir"], "*.yml"))):
    text = open(path).read()
    meta = yaml.safe_load(text)["app"]
    if meta["name"] in by_name and meta["name"] in IN.get("reimport", []):
        # Explicit request (-e dify_reimport_apps=[...]): the DSL changed in the repo, replace the app.
        call("DELETE", f"/apps/{by_name.pop(meta['name'])['id']}")
        print("app:", meta["name"], "deleted for re-import")
    if meta["name"] in by_name:
        app_id, mode = by_name[meta["name"]]["id"], meta["mode"]
        changed = attach_dataset(app_id, mode)
        if changed and mode == "advanced-chat":
            call("POST", f"/apps/{app_id}/workflows/publish", json={})
        print("app:", meta["name"], "already imported" + (", knowledge base attached" if changed else ""))
        continue
    res = call("POST", "/apps/imports", ok=(200, 201, 202), json={"mode": "yaml-content", "yaml_content": text})
    if res.get("status") == "pending":
        res = call("POST", f"/apps/imports/{res['id']}/confirm", ok=(200, 201))
    if res.get("status") != "completed":
        print("FAIL import", meta["name"], json.dumps(res)[:400])
        sys.exit(1)
    app_id, mode = res["app_id"], meta["mode"]
    attach_dataset(app_id, mode)
    if mode in ("advanced-chat", "workflow"):
        call("POST", f"/apps/{app_id}/workflows/publish", json={})
    print("app:", meta["name"], "imported", mode, app_id)
