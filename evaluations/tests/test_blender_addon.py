"""The Blender add-on's pure parts and the device sign-in helpers (ADR-0610, WP-245). No Blender, no network.

The add-on is loaded with stand-in bpy/bmesh/mathutils (evaluations/blender/bpy_stub.py, which restores sys.modules);
the SSE parser runs against a local HTTP server that speaks like the ai-gateway.

Run from the repository root: python3 evaluations/tests/test_blender_addon.py
"""
from __future__ import annotations

import json
import pathlib
import ssl
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "blender"))

import device_login as d  # noqa: E402
from bpy_stub import load_addon  # noqa: E402

z = load_addon()


class StaticCheck(unittest.TestCase):
    OK = """import bpy
import math
from mathutils import Vector
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.5))
leg = bpy.context.active_object
leg.scale = (0.1, 0.1, 1)
bpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=1, location=Vector((1, 0, 0)))
"""

    def test_a_plain_bpy_script_passes(self):
        self.assertEqual(z.check_script(self.OK), [])

    def test_dangerous_constructs_are_refused(self):
        for code, needle in (("import os\nos.system('x')", "import os"), ("import subprocess", "import subprocess"),
                             ("from os import path", "from os"), ("exec('1')", "exec"),
                             ("open('/etc/passwd')", "open"), ("__import__('os')", "__import__"),
                             ("x = ().__class__.__bases__", "__class__"),
                             ("import bpy\nbpy.ops.wm.quit_blender()", "bpy.ops.wm"),
                             ("import bpy\nbpy.utils.register_class(None)", "bpy.utils"),
                             ("import bpy\nbpy.app.handlers.load_post.append(1)", "bpy.app.handlers"),
                             ("def f(:", "syntax error"), ("from . import x", "from None"),
                             ("getattr(bpy, 'ops')", "getattr")):
            with self.subTest(needle):
                problems = z.check_script(code)
                self.assertTrue(any(needle in p for p in problems), problems)

    def test_markdown_is_reduced_to_code(self):
        self.assertEqual(z.extract_code("```python\nimport bpy\n```\nNotes"), "import bpy")
        self.assertEqual(z.extract_code("Here:\n```\nimport bpy\nx=1\n```"), "import bpy\nx=1")
        self.assertEqual(z.extract_code("import bpy\n"), "import bpy")


class Settings(unittest.TestCase):
    def test_endpoints_follow_the_domain_unless_overridden(self):
        self.assertEqual(z.endpoints("apps.example.com"),
                         ("https://ai-gateway.apps.example.com", "https://keycloak.apps.example.com/realms/zuno"))
        self.assertEqual(z.endpoints("x", "https://gw/", "https://kc/realms/zuno/")[0], "https://gw")

    def test_tls_is_always_verified(self):
        ctx = z._ssl_context("")
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)

    def test_the_call_names_the_blender_task_not_a_model(self):
        self.assertEqual((z.AGENT, z.TASK, z.MODEL, z.CLIENT_ID), ("blender", "bpy", "auto", "blender"))

    def test_the_stub_loader_restores_sys_modules(self):
        self.assertNotIn("bpy", sys.modules)


class _Gateway(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body["stream"] is True
        assert (self.headers["X-Zuno-Agent"], self.headers["X-Zuno-Task"]) == ("blender", "bpy")
        if self.path == "/deny":
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"forbidden"}')
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for piece in ["```python\nimport bpy\n", "bpy.ops.mesh.primitive_cube_add()\n", "```"]:
            self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': piece}}]})}\n\n".encode())
            self.wfile.flush()
            time.sleep(0.05)
        self.wfile.write(b"data: [DONE]\n\n")


class Streaming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), _Gateway)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_deltas_are_joined_into_the_script(self):
        status, text = z._stream_chat(self.url + "/ok", {"model": "auto", "messages": []}, None, "t")
        self.assertEqual(status, 200)
        self.assertEqual(z.extract_code(text), "import bpy\nbpy.ops.mesh.primitive_cube_add()")

    def test_an_http_refusal_is_returned_not_raised(self):
        status, err = z._stream_chat(self.url + "/deny", {"model": "auto", "messages": []}, None, "t")
        self.assertEqual((status, err["error"]), (403, "forbidden"))


class DeviceLogin(unittest.TestCase):
    GRANT = ('<form class="form-actions" action="https://kc/realms/zuno/login-actions/consent?client_id=blender&amp;tab_id=1" '
             'method="POST"><input type="hidden" name="code" value="abc"><input name="accept" type="submit" value="Yes"></form>')

    def test_the_grant_page_is_accepted_with_its_hidden_fields(self):
        form = d.grant_form(self.GRANT)
        self.assertEqual(form["action"], "https://kc/realms/zuno/login-actions/consent?client_id=blender&tab_id=1")
        self.assertEqual((form["code"], form["accept"]), ("abc", "Yes"))
        self.assertIsNone(d.grant_form("<html>Device Login Successful</html>"))

    def test_poll_outcomes(self):
        self.assertEqual(d.poll_outcome(200, {"access_token": "t"}), "token")
        self.assertEqual(d.poll_outcome(400, {"error": "authorization_pending"}), "pending")
        self.assertEqual(d.poll_outcome(400, {"error": "slow_down"}), "slow_down")
        self.assertEqual(d.poll_outcome(400, {"error": "expired_token"}), "error:expired_token")
        self.assertEqual(d.poll_outcome(502, {}), "error:http_502")

    def test_errors_never_carry_secrets(self):
        self.assertTrue(issubclass(d.PersonaRefused, d.DeviceLoginError))
        self.assertNotIn("password", str(d.PersonaRefused("Keycloak refused the sign-in of eval-ai-dev-01")))


if __name__ == "__main__":
    unittest.main()
