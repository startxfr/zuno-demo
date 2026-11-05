"""zuno-token-proxy (ADR-0601): token refresh, failure mode, header ownership, streaming passthrough.

Keycloak and both gateways are httpx mock transports; the clock is injected.

Run from the component directory:

    cd components/zuno-token-proxy && python3 tests/test_token_proxy.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import unittest
from typing import Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app import metrics  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.token import TokenSource, TokenUnavailable  # noqa: E402

SETTINGS = Settings(
    token_url="https://keycloak.apps.example/realms/zuno/protocol/openid-connect/token",
    client_id="dify",
    client_secret="s3cret",
    ai_gateway_url="http://ai-gateway.test:8080",
    mcp_gateway_url="http://mcp-gateway.test:8080",
    ai_headers={"X-Zuno-Agent": "dify", "X-Zuno-Task": "chat"},
    mcp_headers={"X-Zuno-Agent": "dify", "X-Zuno-Task": "chat", "X-Zuno-Data-Classification": "C2"},
)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeKeycloak:
    def __init__(self, lifetime: int = 300) -> None:
        self.lifetime = lifetime
        self.calls: List[httpx.Request] = []
        self.down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.down:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, json={"access_token": f"tok-{len(self.calls)}", "expires_in": self.lifetime})


class FakeGateways:
    def __init__(self) -> None:
        self.seen: List[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if request.url.host == "ai-gateway.test" and request.url.path == "/v1/chat/completions":
            body = json.loads(request.content)
            if body.get("stream"):
                chunks = [b'data: {"choices":[{"delta":{"content":"he"}}]}\n\n',
                          b'data: {"choices":[{"delta":{"content":"llo"}}]}\n\n', b"data: [DONE]\n\n"]
                return _streamed(200, headers={"content-type": "text/event-stream"}, raw=b"".join(chunks))
            return _streamed(200, {"choices": [{"message": {"content": "hello"}}]})
        if request.url.host == "ai-gateway.test" and request.url.path == "/v1/models":
            return _streamed(200, {"data": [{"id": "auto"}]})
        if request.url.host == "mcp-gateway.test" and request.url.path == "/mcp":
            return _streamed(200, {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}},
                             headers={"mcp-session-id": "sess-1"})
        return _streamed(404, {"error": "not found"})


def _streamed(status: int, payload: object = None, headers: Dict[str, str] = None, raw: bytes = None) -> httpx.Response:
    """A response that is not read yet, as a real transport returns it."""
    body = raw if raw is not None else json.dumps(payload).encode()
    hdrs = {"content-type": "application/json", **(headers or {})}
    return httpx.Response(status, headers=hdrs, stream=httpx.ByteStream(body))


def _headers(request: httpx.Request) -> Dict[str, str]:
    return {k.lower(): v for k, v in request.headers.items()}


class TokenSourceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        metrics.reset()
        self.clock = Clock()
        self.kc = FakeKeycloak(lifetime=300)
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(self.kc.handler))
        self.source = TokenSource(SETTINGS, self.client, clock=self.clock)

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_the_token_is_cached_until_70_percent_of_its_lifetime(self) -> None:
        self.assertEqual(await self.source.get(), "tok-1")
        self.clock.now += 209
        self.assertEqual(await self.source.get(), "tok-1")
        self.clock.now += 2
        self.assertEqual(await self.source.get(), "tok-2")
        self.assertEqual(len(self.kc.calls), 2)

    async def test_the_grant_is_client_credentials_with_basic_auth(self) -> None:
        await self.source.get()
        request = self.kc.calls[0]
        self.assertEqual(request.content, b"grant_type=client_credentials")
        self.assertTrue(_headers(request)["authorization"].startswith("Basic "))

    async def test_a_failed_refresh_keeps_the_still_valid_token(self) -> None:
        await self.source.get()
        self.kc.down = True
        self.clock.now += 250
        self.assertEqual(await self.source.get(), "tok-1")
        self.assertEqual(metrics.value("zuno_token_proxy_refresh_total", result="error"), 1)

    async def test_no_token_once_the_current_one_expired_and_keycloak_is_down(self) -> None:
        await self.source.get()
        self.kc.down = True
        self.clock.now += 296
        with self.assertRaises(TokenUnavailable):
            await self.source.get()

    async def test_keycloak_down_from_the_start_means_no_token(self) -> None:
        self.kc.down = True
        with self.assertRaises(TokenUnavailable):
            await self.source.get()
        self.assertFalse(self.source.ready)


class ProxyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        metrics.reset()
        self.kc = FakeKeycloak()
        self.gw = FakeGateways()
        self.app = create_app(SETTINGS, token_transport=httpx.MockTransport(self.kc.handler),
                              upstream_transport=httpx.MockTransport(self.gw.handler))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://proxy")

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_the_dummy_key_is_replaced_by_the_fresh_token(self) -> None:
        response = await self.client.post("/v1/chat/completions", headers={"Authorization": "Bearer dummy"},
                                          json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_headers(self.gw.seen[0])["authorization"], "Bearer tok-1")

    async def test_fixed_headers_replace_the_clients_own(self) -> None:
        await self.client.post("/v1/chat/completions", json={"messages": []},
                               headers={"X-Zuno-Agent": "unifai", "x-zuno-task": "admin", "X-Other": "kept"})
        seen = _headers(self.gw.seen[0])
        self.assertEqual(seen["x-zuno-agent"], "dify")
        self.assertEqual(seen["x-zuno-task"], "chat")
        self.assertEqual(seen["x-other"], "kept")
        self.assertNotIn("x-zuno-data-classification", seen)

    async def test_a_client_cannot_add_a_trusted_header_the_config_does_not_own(self) -> None:
        # Only the configured headers are owned; anything else is the gateways' business (ADR-0587
        # clause 1: the client is not in TRUSTED_PLATFORM_CLIENTS, so the ai-gateway ignores it).
        await self.client.post("/v1/chat/completions", json={"messages": []}, headers={"X-Zuno-Quota-Class": "x"})
        self.assertEqual(_headers(self.gw.seen[0])["x-zuno-quota-class"], "x")

    async def test_a_streamed_chat_is_relayed_chunk_for_chunk(self) -> None:
        async with self.client.stream("POST", "/v1/chat/completions", json={"stream": True, "messages": []}) as r:
            self.assertEqual(r.headers["content-type"], "text/event-stream")
            body = b"".join([chunk async for chunk in r.aiter_raw()])
        self.assertIn(b"data: [DONE]", body)
        self.assertIn(b'"llo"', body)

    async def test_models_and_query_strings_reach_the_ai_gateway(self) -> None:
        response = await self.client.get("/v1/models?x=1")
        self.assertEqual(response.json()["data"][0]["id"], "auto")
        self.assertEqual(str(self.gw.seen[0].url), "http://ai-gateway.test:8080/v1/models?x=1")

    async def test_mcp_gets_its_own_headers_and_keeps_the_session(self) -> None:
        response = await self.client.post("/mcp", headers={"mcp-session-id": "sess-1"},
                                          json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(response.headers["mcp-session-id"], "sess-1")
        seen = _headers(self.gw.seen[0])
        self.assertEqual(str(self.gw.seen[0].url), "http://mcp-gateway.test:8080/mcp")
        self.assertEqual(seen["x-zuno-data-classification"], "C2")
        self.assertEqual(seen["mcp-session-id"], "sess-1")
        self.assertEqual(seen["authorization"], "Bearer tok-1")

    async def test_no_token_means_503_and_nothing_relayed(self) -> None:
        self.kc.down = True
        response = await self.client.post("/v1/chat/completions", json={"messages": []})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.gw.seen, [])
        self.assertEqual((await self.client.get("/readyz")).status_code, 503)
        self.assertEqual(metrics.value("zuno_token_proxy_requests_total", upstream="ai-gateway", code="503"), 1)

    async def test_an_unreachable_gateway_is_a_502(self) -> None:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)
        app = create_app(SETTINGS, token_transport=httpx.MockTransport(self.kc.handler),
                         upstream_transport=httpx.MockTransport(refuse))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as client:
            self.assertEqual((await client.get("/mcp")).status_code, 502)

    async def test_other_paths_are_not_relayed(self) -> None:
        self.assertEqual((await self.client.get("/admin")).status_code, 404)
        self.assertEqual(self.gw.seen, [])

    async def test_metrics_are_exposed(self) -> None:
        await self.client.get("/v1/models")
        text = (await self.client.get("/metrics")).text
        self.assertIn('zuno_token_proxy_refresh_total{result="success"} 1', text)
        self.assertIn('zuno_token_proxy_requests_total{code="200",upstream="ai-gateway"} 1', text)


class SettingsTests(unittest.TestCase):
    def test_required_settings(self) -> None:
        with self.assertRaises(ValueError):
            Settings.from_env({"TOKEN_URL": "https://k", "CLIENT_ID": "dify"})

    def test_headers_and_urls_from_env(self) -> None:
        s = Settings.from_env({"TOKEN_URL": "https://k", "CLIENT_ID": "kagent", "CLIENT_SECRET": "x",
                               "AI_GATEWAY_URL": "http://a:8080/", "MCP_HEADERS": '{"X-Zuno-Agent": "kagent"}'})
        self.assertEqual(s.ai_gateway_url, "http://a:8080")
        self.assertEqual(s.mcp_headers, {"X-Zuno-Agent": "kagent"})

    def test_bad_headers_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            Settings.from_env({"TOKEN_URL": "https://k", "CLIENT_ID": "a", "CLIENT_SECRET": "x", "AI_HEADERS": "[1]"})


if __name__ == "__main__":
    unittest.main()
