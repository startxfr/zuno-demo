"""Zuno 3D generator: a Blender add-on that asks the platform's local model for a bpy script (ADR-0610).

Install: Edit > Preferences > Add-ons > (menu) Install from Disk, pick this file, tick the add-on. Then in the 3D
Viewport press N, open the "Zuno 3D" tab, set the cluster domain, Sign in (OAuth device flow in the browser, Keycloak
client `blender`), type a prompt, Generate script, read it in the Text Editor, Run script.

The call goes to https://ai-gateway.<domain> with the user's own token, X-Zuno-Agent: blender and X-Zuno-Task: bpy;
the platform keeps it on local models (C3 floor). The returned script is shown, statically checked (not a sandbox)
and runs only on the user's click, all or nothing. Tokens live in memory only; TLS is always verified.
"""

bl_info = {
    "name": "Zuno 3D generator (demo)",
    "author": "Zuno Demo",
    "version": (0, 2, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Zuno 3D",
    "description": "Generates editable objects from a prompt with a local model through the Zuno ai-gateway (ADR-0610)",
    "category": "Object",
}

import ast
import json
import math
import random
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

import bmesh
import bpy
import mathutils

# ADR-0610: the ai-gateway routes on (agent, task); the model name is not a routing input.
MODEL = "auto"
AGENT = "blender"
TASK = "bpy"
CLIENT_ID = "blender"
TEXT_NAME = "zuno_3d_script.py"
# v2 (2026-11-07, WP-245): the first prompt's failures were API inventions (an unknown `diameter1`, bmesh operators
# that do not exist, unlinking objects from collections); this one keeps the model on documented primitives.
SYSTEM_PROMPT = (
    "You are an expert Blender 4.2 Python (bpy) developer. Return ONLY executable Python code for Blender, with no "
    "Markdown fences and no explanation. Rules: "
    "1) Import only bpy, math and mathutils; do not use bmesh. "
    "2) Build every part with bpy.ops.mesh.primitive_cube_add, primitive_cylinder_add, primitive_cone_add, "
    "primitive_uv_sphere_add, primitive_torus_add or primitive_plane_add, passing only these keyword arguments: "
    "size, radius, radius1, radius2, depth, major_radius, minor_radius, vertices, location, rotation, scale. "
    "3) After each add, take the new object from bpy.context.active_object, give it a name, then set its scale or "
    "rotation if needed. "
    "4) Never link, unlink or move objects between collections, never delete objects, never save files or quit "
    "Blender. "
    "5) Give the parts simple materials: bpy.data.materials.new(name), use_nodes = True, then set "
    "nodes['Principled BSDF'].inputs['Base Color'].default_value, and append the material to obj.data.materials. "
    "6) Rest the object on the ground (z >= 0) and make its parts touch each other, like one real object."
)
ALLOWED_IMPORTS = {"bpy", "bmesh", "mathutils", "math", "random"}
FORBIDDEN_CALLS = {"exec", "eval", "compile", "open", "__import__", "getattr", "setattr", "delattr",
                   "globals", "locals", "vars", "input", "breakpoint"}
FORBIDDEN_PREFIXES = ("bpy.ops.wm", "bpy.ops.script", "bpy.ops.preferences", "bpy.utils", "bpy.app.handlers")

# Tokens and job results live in process memory only (ADR-0610 clause 4).
_state = {"access": None, "refresh": None, "expires_at": 0.0, "user_code": "", "verify_url": "",
          "status": "Signed out", "busy": False, "result": None, "error": None, "check": ""}


# ---------- pure helpers ----------

def extract_code(text):
    """Return the first fenced block if the model added fences, else the text."""
    match = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return (match.group(1) if match else text).strip()


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def check_script(code):
    """Static guard against a confused model. Not a sandbox. Returns a list of problems."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax error line {exc.lineno}: {exc.msg}"]
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_IMPORTS:
                    problems.append(f"line {node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS or node.level:
                problems.append(f"line {node.lineno}: from {node.module} import ...")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            problems.append(f"line {node.lineno}: call to {node.func.id}()")
        elif isinstance(node, ast.Name) and node.id.startswith("__"):
            problems.append(f"line {node.lineno}: name {node.id}")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                problems.append(f"line {node.lineno}: attribute {node.attr}")
            dotted = _dotted(node)
            if dotted and dotted.startswith(FORBIDDEN_PREFIXES):
                problems.append(f"line {node.lineno}: {dotted}")
    return sorted(set(problems))


def endpoints(domain, gateway_override="", issuer_override=""):
    """(gateway URL, Keycloak issuer URL) for a cluster apps domain, unless overridden."""
    domain = (domain or "").strip().strip("/")
    gateway = (gateway_override or f"https://ai-gateway.{domain}").rstrip("/")
    issuer = (issuer_override or f"https://keycloak.{domain}/realms/zuno").rstrip("/")
    return gateway, issuer


def _ssl_context(ca_file):
    ctx = ssl.create_default_context()  # verification stays on (ADR-0610 clause 7)
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass
    if ca_file:
        ctx.load_verify_locations(bpy.path.abspath(ca_file))
    return ctx


def _post(url, data, ctx, headers=None, form=True, timeout=30):
    body = urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode()
    hdrs = {"Content-Type": "application/x-www-form-urlencoded" if form else "application/json"}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        try:
            return err.code, json.loads(err.read().decode())
        except ValueError:
            return err.code, {"error": f"HTTP {err.code}"}


def _store_tokens(tok):
    _state["access"] = tok["access_token"]
    _state["refresh"] = tok.get("refresh_token")
    _state["expires_at"] = time.time() + int(tok.get("expires_in", 300)) - 30


# ---------- background jobs (no bpy calls in threads) ----------

def _sign_in_job(issuer, ctx):
    status, dev = _post(f"{issuer}/protocol/openid-connect/auth/device",
                        {"client_id": CLIENT_ID, "scope": "openid"}, ctx)
    if status != 200:
        _state.update(busy=False, error=f"device sign-in refused: {dev.get('error', status)}")
        return
    _state.update(user_code=dev["user_code"],
                  verify_url=dev.get("verification_uri_complete") or dev["verification_uri"],
                  status="Waiting for browser sign-in")
    interval = int(dev.get("interval", 5))
    deadline = time.time() + int(dev.get("expires_in", 600))
    while time.time() < deadline:
        time.sleep(interval)
        status, tok = _post(f"{issuer}/protocol/openid-connect/token",
                            {"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                             "device_code": dev["device_code"], "client_id": CLIENT_ID}, ctx)
        if status == 200:
            _store_tokens(tok)
            _state.update(busy=False, user_code="", verify_url="", status="Signed in")
            return
        err = tok.get("error")
        if err == "slow_down":
            interval += 5
        elif err != "authorization_pending":
            _state.update(busy=False, user_code="", error=f"sign-in failed: {err}")
            return
    _state.update(busy=False, user_code="", error="sign-in timed out")


def _token(issuer, ctx):
    if _state["access"] and time.time() < _state["expires_at"]:
        return _state["access"]
    if _state["refresh"]:
        status, tok = _post(f"{issuer}/protocol/openid-connect/token",
                            {"grant_type": "refresh_token", "refresh_token": _state["refresh"],
                             "client_id": CLIENT_ID}, ctx)
        if status == 200:
            _store_tokens(tok)
            return _state["access"]
    _state.update(access=None, refresh=None, status="Signed out")
    return None


def _stream_chat(url, payload, ctx, token, timeout=240):
    """POST with stream=true and join the content deltas. Streaming keeps bytes flowing, so a load balancer's idle
    timeout (60 s on demo333's AWS ELB) cannot cut a long generation. Returns (status, text or error dict)."""
    body = json.dumps(dict(payload, stream=True)).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json", "Accept": "text/event-stream", "Authorization": f"Bearer {token}",
        "X-Zuno-Agent": AGENT, "X-Zuno-Task": TASK})
    try:
        resp = urllib.request.urlopen(req, context=ctx, timeout=timeout)
    except urllib.error.HTTPError as err:
        try:
            return err.code, json.loads(err.read().decode())
        except ValueError:
            return err.code, {"error": f"HTTP {err.code}"}
    parts = []
    with resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except ValueError:
                continue
            if chunk.get("error"):
                return 502, chunk
            for choice in chunk.get("choices") or []:
                parts.append((choice.get("delta") or {}).get("content") or "")
    return 200, "".join(parts)


def _generate_job(gateway, issuer, ctx, prompt):
    token = _token(issuer, ctx)
    if not token:
        _state.update(busy=False, error="session expired: sign in again")
        return
    payload = {"model": MODEL, "temperature": 0.2,
               "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": f"Create this 3D object or scene: {prompt}"}]}
    try:
        status, res = _stream_chat(f"{gateway.rstrip('/')}/v1/chat/completions", payload, ctx, token)
    except Exception as exc:  # network, TLS, a cut stream
        _state.update(busy=False, error=f"gateway unreachable: {exc}")
        return
    if status != 200:
        _state.update(busy=False, error=f"gateway answered {status}: {res.get('error', res)}")
        return
    if not res.strip():
        _state.update(busy=False, error="the model returned an empty answer")
        return
    _state.update(busy=False, result=res)


def _poll():
    """Main-thread timer: hands results back to Blender."""
    if _state["result"] is not None:
        code = extract_code(_state["result"])
        _state["result"] = None
        text = bpy.data.texts.get(TEXT_NAME) or bpy.data.texts.new(TEXT_NAME)
        text.clear()
        text.write(code)
        problems = check_script(code)
        _state["check"] = "Check passed: review the script, then Run" if not problems else \
            "Refused: " + "; ".join(problems[:3])
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type in {"VIEW_3D", "TEXT_EDITOR"}:
                area.tag_redraw()
    return 0.5 if (_state["busy"] or _state["user_code"]) else None


def _start(job, *args):
    _state.update(busy=True, error=None)
    threading.Thread(target=job, args=args, daemon=True).start()
    if not bpy.app.timers.is_registered(_poll):
        bpy.app.timers.register(_poll, first_interval=0.5)


# ---------- Blender UI ----------

class ZUNO3D_Settings(bpy.types.PropertyGroup):
    domain: bpy.props.StringProperty(name="Cluster domain", default="apps.demo333.startx.fr",
                                     description="The cluster's apps domain: the gateway is ai-gateway.<domain>")
    gateway_url: bpy.props.StringProperty(name="Gateway override", default="",
                                          description="Empty: https://ai-gateway.<domain>")
    issuer_url: bpy.props.StringProperty(name="Issuer override", default="",
                                         description="Empty: https://keycloak.<domain>/realms/zuno")
    ca_file: bpy.props.StringProperty(name="CA file", subtype="FILE_PATH",
                                      description="Only for a cluster whose routes use a private CA")
    show_advanced: bpy.props.BoolProperty(name="Advanced", default=False)
    prompt: bpy.props.StringProperty(name="Prompt",
                                     default="A wooden table with 4 cylindrical legs and a small desk lamp on top")


def _endpoints(s):
    return endpoints(s.domain, s.gateway_url, s.issuer_url)


class ZUNO3D_OT_sign_in(bpy.types.Operator):
    bl_idname = "zuno3d.sign_in"
    bl_label = "Sign in"

    def execute(self, context):
        s = context.scene.zuno3d
        _start(_sign_in_job, _endpoints(s)[1], _ssl_context(s.ca_file))
        return {"FINISHED"}


class ZUNO3D_OT_open_browser(bpy.types.Operator):
    bl_idname = "zuno3d.open_browser"
    bl_label = "Open sign-in page"

    def execute(self, context):
        webbrowser.open(_state["verify_url"])
        return {"FINISHED"}


class ZUNO3D_OT_sign_out(bpy.types.Operator):
    bl_idname = "zuno3d.sign_out"
    bl_label = "Sign out"

    def execute(self, context):
        _state.update(access=None, refresh=None, expires_at=0.0, status="Signed out")
        return {"FINISHED"}


class ZUNO3D_OT_generate(bpy.types.Operator):
    bl_idname = "zuno3d.generate"
    bl_label = "Generate script"

    def execute(self, context):
        s = context.scene.zuno3d
        if not s.prompt.strip():
            self.report({"WARNING"}, "The prompt is empty")
            return {"CANCELLED"}
        _state["check"] = ""
        gateway, issuer = _endpoints(s)
        _start(_generate_job, gateway, issuer, _ssl_context(s.ca_file), s.prompt)
        self.report({"INFO"}, "Asking the platform's local model...")
        return {"FINISHED"}


class ZUNO3D_OT_run(bpy.types.Operator):
    bl_idname = "zuno3d.run"
    bl_label = "Run script"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        text = bpy.data.texts.get(TEXT_NAME)
        if text is None:
            self.report({"WARNING"}, "Generate a script first")
            return {"CANCELLED"}
        code = text.as_string()  # the user's edits count
        problems = check_script(code)
        if problems:
            self.report({"ERROR"}, "Refused: " + "; ".join(problems[:3]))
            return {"CANCELLED"}
        scope = {"__name__": "__zuno3d__", "bpy": bpy, "bmesh": bmesh, "mathutils": mathutils,
                 "math": math, "random": random}
        before = set(bpy.data.objects)
        try:
            exec(compile(code, TEXT_NAME, "exec"), scope)  # after the check and the user's click only
        except Exception as exc:
            # All or nothing: a script that fails half-way (an invented API argument) leaves no partial objects.
            for obj in set(bpy.data.objects) - before:
                bpy.data.objects.remove(obj, do_unlink=True)
            self.report({"ERROR"}, f"Script failed, nothing kept: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"{len(set(bpy.data.objects) - before)} objects created")
        return {"FINISHED"}


class ZUNO3D_PT_panel(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Zuno 3D"
    bl_label = "Zuno 3D (local model)"

    def draw(self, context):
        s = context.scene.zuno3d
        col = self.layout.column()
        box = col.box()
        box.prop(s, "domain")
        box.prop(s, "show_advanced")
        if s.show_advanced:
            box.prop(s, "gateway_url")
            box.prop(s, "issuer_url")
            box.prop(s, "ca_file")
        col.label(text=f"Task: {AGENT}/{TASK}   Status: {_state['status']}")
        if _state["user_code"]:
            col.label(text=f"Code: {_state['user_code']}")
            col.operator("zuno3d.open_browser", icon="URL")
        row = col.row()
        row.enabled = not _state["busy"]
        row.operator("zuno3d.sign_in", icon="USER")
        row.operator("zuno3d.sign_out")
        col.prop(s, "prompt", text="")
        row = col.row()
        row.enabled = bool(_state["access"]) and not _state["busy"]
        row.operator("zuno3d.generate", icon="TEXT")
        if _state["busy"]:
            col.label(text="Working...", icon="TIME")
        if _state["check"]:
            col.label(text=_state["check"])
        col.operator("zuno3d.run", icon="PLAY")
        if _state["error"]:
            col.label(text=_state["error"], icon="ERROR")


CLASSES = (ZUNO3D_Settings, ZUNO3D_OT_sign_in, ZUNO3D_OT_open_browser, ZUNO3D_OT_sign_out,
           ZUNO3D_OT_generate, ZUNO3D_OT_run, ZUNO3D_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.zuno3d = bpy.props.PointerProperty(type=ZUNO3D_Settings)


def unregister():
    if bpy.app.timers.is_registered(_poll):
        bpy.app.timers.unregister(_poll)
    del bpy.types.Scene.zuno3d
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    _state.update(access=None, refresh=None)


if __name__ == "__main__":
    register()
