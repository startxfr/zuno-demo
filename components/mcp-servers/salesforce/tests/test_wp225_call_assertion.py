#!/usr/bin/env python3
"""WP-225 lot C (ADR-0602 clause 10, ADR-0603 M14): this server verifies the
per-call assertion of the mcp-gateway (CallAssertionMiddleware).

The assertions are minted by the gateway's own module
(components/mcp-gateway/app/call_assertion.py), so the signer and this verifier
are tested together. This file is byte-identical in confluence, git-forge,
salesforce and aap; it reads the server's backend name from the server itself.

Run from the server directory:

    python3 tests/test_wp225_call_assertion.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import pathlib
import sys
import time
import unittest
from unittest import mock

_HERE = pathlib.Path(__file__).resolve()
_SERVER_DIR = _HERE.parents[1]
_REPO_ROOT = _HERE.parents[4]
sys.path.insert(0, str(_SERVER_DIR))
# What each of the four servers needs at import time (one file for all four).
for _name, _value in {
    "MCP_GATEWAY_WORKLOAD_TOKEN": "test-workload-token",
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


def _load_gateway_module():
    path = _REPO_ROOT / "components" / "mcp-gateway" / "app" / "call_assertion.py"
    spec = importlib.util.spec_from_file_location("gateway_call_assertion", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ca = _load_gateway_module()
AUD = server.CALLER_CONTEXT_AUDIENCE
KEY = Ed25519PrivateKey.generate()
OTHER = Ed25519PrivateKey.generate()
PUBLIC_PEM = KEY.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
).decode()


def _call(name, rid=1):
    return json.dumps({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                       "params": {"name": name, "arguments": {}}}).encode()


def _run(authorization=None, body=b"", env=None, method="POST"):
    """Send one request through CallAssertionMiddleware to an app that echoes the body."""
    reached = {}

    async def app(scope, receive, send):
        body, more = b"", True
        while more:
            message = await receive()
            body += message.get("body", b"")
            more = message.get("more_body", False)
        reached["body"] = body
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = server.CallAssertionMiddleware(app)
    headers = [(b"content-type", b"application/json")]
    if authorization:
        headers.append((b"authorization", authorization.encode()))
    scope = {"type": "http", "method": method, "path": "/mcp", "headers": headers, "query_string": b""}
    chunks = [body[:7], body[7:]] if body else [b""]
    queue = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)]
    sent = []

    async def receive():
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    with mock.patch.dict(os.environ, env or {}, clear=False):
        asyncio.run(middleware(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    return status, reached


def _assertion(tool="t", aud=AUD, key=KEY, now=None, ttl=60):
    return "Bearer " + ca.mint(audience=aud, sub="consultant-01", tool=tool, key=key, ttl=ttl, now=now)


ON = {"MCP_CALL_ASSERTION_PUBLIC_KEY": PUBLIC_PEM}
REQUIRED = {**ON, "MCP_CALL_ASSERTION_REQUIRED": "true"}


class CallAssertionTest(unittest.TestCase):
    def setUp(self):
        server._CALL_ASSERTION_SEEN.clear()
        os.environ.pop("MCP_CALL_ASSERTION_PUBLIC_KEY", None)
        os.environ.pop("MCP_CALL_ASSERTION_REQUIRED", None)

    def test_registered_on_the_mcp_app(self):
        self.assertIn(server.CallAssertionMiddleware, [m.cls for m in server.mcp_asgi_app.user_middleware])

    def test_off_by_default_a_user_bearer_passes_as_before(self):
        status, reached = _run("Bearer some.user.jwt", _call("t"))
        self.assertEqual(status, 200)
        self.assertEqual(reached["body"], _call("t"), "the body reaches the app intact")

    def test_a_valid_assertion_for_this_tool_is_served_and_the_body_is_replayed(self):
        status, reached = _run(_assertion("t"), _call("t"), env=REQUIRED)
        self.assertEqual(status, 200)
        self.assertEqual(reached["body"], _call("t"))

    def test_required_refuses_a_request_without_an_assertion(self):
        self.assertEqual(_run(None, _call("t"), env=REQUIRED)[0], 401)
        self.assertEqual(_run("Bearer some.user.jwt", _call("t"), env=REQUIRED)[0], 401)

    def test_required_without_a_key_refuses_everything(self):
        self.assertEqual(_run(_assertion("t"), _call("t"), env={"MCP_CALL_ASSERTION_REQUIRED": "true"})[0], 401)

    def test_a_forged_assertion_is_refused(self):
        self.assertEqual(_run(_assertion("t", key=OTHER), _call("t"), env=ON)[0], 401)
        token = _assertion("t")
        self.assertEqual(_run(token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB"), _call("t"), env=ON)[0], 401)

    def test_an_expired_assertion_is_refused(self):
        self.assertEqual(_run(_assertion("t", now=time.time() - 120), _call("t"), env=ON)[0], 401)

    def test_an_assertion_dated_in_the_future_is_refused(self):
        self.assertEqual(_run(_assertion("t", now=time.time() + 120), _call("t"), env=ON)[0], 401)

    def test_an_assertion_for_another_backend_is_refused(self):
        other = "confluence" if AUD != "confluence" else "aap"
        self.assertEqual(_run(_assertion("t", aud=other), _call("t"), env=ON)[0], 401)

    def test_an_assertion_for_another_tool_is_refused(self):
        self.assertEqual(_run(_assertion("t"), _call("u"), env=ON)[0], 403)

    def test_a_replayed_assertion_is_refused(self):
        token = _assertion("t")
        self.assertEqual(_run(token, _call("t"), env=ON)[0], 200)
        self.assertEqual(_run(token, _call("t", rid=2), env=ON)[0], 403)

    def test_one_assertion_covers_one_tool_call_only(self):
        batch = b"[" + _call("t") + b"," + _call("t", rid=2) + b"]"
        self.assertEqual(_run(_assertion("t"), batch, env=ON)[0], 403)

    def test_the_session_requests_of_one_call_do_not_consume_it(self):
        token = _assertion("t")
        init = json.dumps({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}}).encode()
        self.assertEqual(_run(token, init, env=REQUIRED)[0], 200)
        self.assertEqual(_run(token, b"", env=REQUIRED, method="GET")[0], 200)
        self.assertEqual(_run(token, _call("t"), env=REQUIRED)[0], 200)

    def test_a_schema_read_assertion_lists_but_calls_nothing(self):
        token = "Bearer " + ca.mint(audience=AUD, sub=ca.SELF_SUBJECT, tool="", key=KEY)
        listing = json.dumps({"jsonrpc": "2.0", "id": 0, "method": "tools/list", "params": {}}).encode()
        self.assertEqual(_run(token, listing, env=REQUIRED)[0], 200)
        self.assertEqual(_run(token, _call("t"), env=REQUIRED)[0], 403)

    def test_a_lifetime_above_sixty_seconds_is_refused(self):
        import jwt

        now = int(time.time())
        claims = {"iss": "mcp-gateway", "aud": AUD, "sub": "s", "act": {"sub": "mcp-gateway"}, "tool": "t",
                  "iat": now, "exp": now + 3600, "jti": "x"}
        token = "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"typ": "zuno-call+jwt"})
        self.assertEqual(_run(token, _call("t"), env=ON)[0], 401)

    def test_an_assertion_without_the_gateway_actor_is_refused(self):
        import jwt

        now = int(time.time())
        claims = {"iss": "mcp-gateway", "aud": AUD, "sub": "s", "tool": "t", "iat": now, "exp": now + 30, "jti": "y"}
        token = "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"typ": "zuno-call+jwt"})
        self.assertEqual(_run(token, _call("t"), env=ON)[0], 401)

    def test_a_real_mcp_session_runs_through_the_middleware(self):
        """The server's own app (session manager, SSE) behind the middleware, with
        MCP_CALL_ASSERTION_REQUIRED: a gateway schema-read assertion lists the
        tools; the same session without an assertion never gets past initialize."""
        import httpx2
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        base = "http://localhost:8000"
        gateway = {"X-Zuno-Gateway-Token": server.GATEWAY_WORKLOAD_TOKEN}

        async def listing(transport, headers):
            client = httpx2.AsyncClient(transport=transport, base_url=base, headers=headers)
            async with streamable_http_client(f"{base}/mcp", http_client=client) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), 10)
                    return [t.name for t in (await session.list_tools()).tools]

        async def scenario():
            transport = httpx2.ASGITransport(app=server.app)
            lifespan = server.app.router.lifespan_context(server.app)
            await lifespan.__aenter__()
            try:
                token = "Bearer " + ca.mint(audience=AUD, sub=ca.SELF_SUBJECT, tool="", key=KEY)
                listed = await listing(transport, {**gateway, "Authorization": token})
                try:
                    await listing(transport, gateway)
                    refused = False
                except BaseException:  # noqa: BLE001 - the SDK wraps the 401 in its task group
                    refused = True
                return listed, refused
            finally:
                await lifespan.__aexit__(None, None, None)

        with mock.patch.dict(os.environ, REQUIRED):
            listed, refused = asyncio.run(scenario())
        self.assertTrue(listed, "the tools are listed with a valid assertion")
        self.assertTrue(refused, "a session without an assertion is refused when required")

    def test_the_block_is_byte_identical_in_the_four_servers(self):
        def block(name):
            text = (_REPO_ROOT / "components" / "mcp-servers" / name / "server.py").read_text()
            start = text.index("# BEGIN call-assertion verifier (WP-225 lot C)")
            end = text.index("# END call-assertion verifier (WP-225 lot C)")
            return text[start:end]

        copies = {name: block(name) for name in ("confluence", "git-forge", "salesforce", "aap")}
        self.assertEqual(len(set(copies.values())), 1, "the call-assertion verifier differs between servers")
        here = (_HERE.parent / "test_wp225_call_assertion.py").read_bytes()
        for name in ("confluence", "git-forge", "salesforce", "aap"):
            other = _REPO_ROOT / "components" / "mcp-servers" / name / "tests" / "test_wp225_call_assertion.py"
            self.assertEqual(other.read_bytes(), here, name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
