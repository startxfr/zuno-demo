#!/usr/bin/env python3
"""WP-250: the caller context rides inside the Transit-signed call assertion (`ctx`).

The middleware hands a VERIFIED `ctx` to the tool code as X-Zuno-Assertion-Caller and strips any such header a
client sent. `_verified_caller` reads it and nothing else: since lot 2 the HMAC-signed headers and the shared
workload token are retired. This file is byte-identical in confluence, git-forge, salesforce and aap; the
assertions are minted by the gateway's own module.

Run from the server directory:

    python3 tests/test_wp250_assertion_caller.py
"""
from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import os
import pathlib
import sys
import unittest
from unittest import mock

_HERE = pathlib.Path(__file__).resolve()
_SERVER_DIR = _HERE.parents[1]
_REPO_ROOT = _HERE.parents[4]
sys.path.insert(0, str(_SERVER_DIR))
for _name, _value in {
    "CONFLUENCE_BASE_URL": "https://example.atlassian.net",
    "CONFLUENCE_EMAIL": "technical@example.com",
    "CONFLUENCE_API_TOKEN": "test-token",
    "GITHUB_TOKEN": "test-github-token",
    "GITLAB_TOKEN": "test-gitlab-token",
    "SALESFORCE_BASE_URL": "https://example.my.salesforce.com",
    "SALESFORCE_ACCESS_TOKEN": "test-access-token",
    "AAP_API_TOKEN": "test-token",
    "AAP_BASE_URL": "http://aap.zuno-aap.svc",
}.items():
    os.environ.setdefault(_name, _value)

import server  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402


def _load(name: str):
    path = _REPO_ROOT / "components" / "mcp-gateway" / "app" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"gateway_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ca = _load("call_assertion")
cc = _load("caller_context")  # assertion_context(): the `ctx` claim
AUD = server.CALLER_CONTEXT_AUDIENCE
KEY = Ed25519PrivateKey.generate()
PEM = KEY.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
ENV = {"MCP_CALL_ASSERTION_PUBLIC_KEY": PEM, "MCP_CALL_ASSERTION_REQUIRED": "true"}
IDENTITY = {"email": "Ana@Example.com", "email_verified": True, "preferred_username": "ana"}
CALLER = cc.assertion_context(groups=["b", "a", "a"], claims=IDENTITY)


def _call(name: str) -> bytes:
    return json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": {}}}).encode()


def _run(headers, body=b""):
    seen = {}

    async def app(scope, receive, send):
        seen["headers"] = {k.decode(): v.decode() for k, v in scope["headers"]}
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    scope = {"type": "http", "method": "POST", "path": "/mcp", "query_string": b"",
             "headers": [(k.encode(), v.encode()) for k, v in headers.items()]}
    queue = [{"type": "http.request", "body": body, "more_body": False}]
    sent = []

    async def receive():
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    with mock.patch.dict(os.environ, ENV, clear=False):
        asyncio.run(server.CallAssertionMiddleware(app)(scope, receive, send))
    return next(m["status"] for m in sent if m["type"] == "http.response.start"), seen.get("headers")


def _bearer(tool="t", caller=CALLER):
    return "Bearer " + ca.mint(audience=AUD, sub="ana-sub", tool=tool, key=KEY, caller=caller)


class AssertionCallerTest(unittest.TestCase):
    def setUp(self):
        server._CALL_ASSERTION_SEEN.clear()

    def test_a_verified_ctx_reaches_the_tool_code(self):
        status, seen = _run({"authorization": _bearer()}, _call("t"))
        self.assertEqual(status, 200)
        caller = server._assertion_caller(seen, "t")
        self.assertEqual(caller, {"sub": "ana-sub", "groups": ["a", "b"], "email": "ana@example.com",
                                  "email_verified": True, "username": "ana"})

    def test_verified_caller_is_the_assertion_caller(self):
        _, seen = _run({"authorization": _bearer()}, _call("t"))
        self.assertEqual(server._verified_caller(seen, "t")["sub"], "ana-sub")

    def test_without_ctx_there_is_no_caller(self):
        _, seen = _run({"authorization": _bearer(caller=None)}, _call("t"))
        self.assertNotIn(server.ASSERTION_CALLER_HEADER, seen)
        self.assertIsNone(server._verified_caller(seen, "t"))

    def test_the_retired_hmac_headers_are_ignored(self):
        _, seen = _run({"authorization": _bearer(caller=None),
                        "x-zuno-caller-context": "e30", "x-zuno-caller-signature": "0" * 64,
                        "x-zuno-gateway-token": "anything"}, _call("t"))
        self.assertIsNone(server._verified_caller(seen, "t"))
        self.assertFalse(hasattr(server, "GATEWAY_WORKLOAD_TOKEN"))
        self.assertFalse(hasattr(server, "GatewayTokenMiddleware"))

    def test_a_request_without_an_assertion_is_refused(self):
        status, _ = _run({}, _call("t"))
        self.assertEqual(status, 401)

    def test_a_header_sent_by_a_client_is_removed(self):
        fake = base64.urlsafe_b64encode(json.dumps(
            {"sub": "eve", "tool": "t", "groups": ["admin"]}).encode()).decode()
        status, seen = _run({"authorization": _bearer(caller=None), "x-zuno-assertion-caller": fake}, _call("t"))
        self.assertEqual(status, 200)
        self.assertNotIn(server.ASSERTION_CALLER_HEADER, seen)

    def test_a_client_header_cannot_replace_the_signed_ctx(self):
        fake = base64.urlsafe_b64encode(json.dumps(
            {"sub": "eve", "tool": "t", "groups": ["admin"]}).encode()).decode()
        _, seen = _run({"authorization": _bearer(), "x-zuno-assertion-caller": fake}, _call("t"))
        self.assertEqual(server._assertion_caller(seen, "t")["sub"], "ana-sub")

    def test_a_ctx_for_another_tool_is_not_used(self):
        _, seen = _run({"authorization": _bearer()}, _call("t"))
        self.assertIsNone(server._assertion_caller(seen, "other"))

    def test_a_malformed_ctx_is_refused(self):
        for bad in ({"groups": "admin"}, {"groups": [1]}, "text", ["x"]):
            server._CALL_ASSERTION_SEEN.clear()
            status, _ = _run({"authorization": _bearer(caller=bad)}, _call("t"))
            self.assertEqual(status, 401, msg=repr(bad))

    def test_a_schema_read_assertion_carries_no_ctx(self):
        token = "Bearer " + ca.mint(audience=AUD, sub=ca.SELF_SUBJECT, tool="", key=KEY, caller=CALLER)
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode()
        status, seen = _run({"authorization": token}, body)
        self.assertEqual(status, 200)
        self.assertNotIn(server.ASSERTION_CALLER_HEADER, seen)

    def test_garbage_in_the_header_is_no_caller(self):
        for raw in ("", "!!!", base64.urlsafe_b64encode(b"[1]").decode()):
            self.assertIsNone(server._assertion_caller({server.ASSERTION_CALLER_HEADER: raw}, "t"))


if __name__ == "__main__":
    unittest.main()
