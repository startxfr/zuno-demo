"""WP-297 (ADR-0619 clause 5): the alternative gateways of zuno-token-proxy.

`/alt/<name>/v1/...` is relayed to that entry's URL with its fixed headers and the same token;
an unknown name is 404 and nothing is relayed; without ALT_GATEWAYS the proxy is as before.
Keycloak and the gateways are httpx mock transports.

Run from the component directory:

    cd components/zuno-token-proxy && python3 tests/test_wp297_alt_gateways.py
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
import ssl
import sys
import unittest
from typing import Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import certifi  # noqa: E402
import httpx  # noqa: E402

from app import metrics  # noqa: E402
from app.config import AltGateway, Settings  # noqa: E402
from app.main import _timeout_for, create_app  # noqa: E402

BASE = Settings(
    token_url="https://keycloak.apps.example/realms/zuno/protocol/openid-connect/token",
    client_id="kagent",
    client_secret="s3cret",
    ai_gateway_url="http://ai-gateway.test:8080",
    mcp_gateway_url="http://mcp-gateway.test:8080",
    ai_headers={"X-Zuno-Agent": "kagent"},
)
ALT = dataclasses.replace(BASE, alt_gateways=(
    AltGateway(name="praxis", url="http://praxis.test:8080/v1", headers={"X-Zuno-Agent": "kagent", "X-Alt": "praxis"}),
    AltGateway(name="slow-one", url="https://slow.test/base/v1", timeout_s=45.0),
))
ENV = {"TOKEN_URL": "https://k", "CLIENT_ID": "kagent", "CLIENT_SECRET": "x"}


def _keycloak(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 300})


class Upstreams:
    def __init__(self) -> None:
        self.seen: List[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        body = json.dumps({"host": request.url.host, "path": request.url.path}).encode()
        return httpx.Response(200, headers={"content-type": "application/json"}, stream=httpx.ByteStream(body))


def _headers(request: httpx.Request) -> Dict[str, str]:
    return {k.lower(): v for k, v in request.headers.items()}


class AltRouteTests(unittest.IsolatedAsyncioTestCase):
    settings = ALT

    async def asyncSetUp(self) -> None:
        metrics.reset()
        self.up = Upstreams()
        self.app = create_app(self.settings, token_transport=httpx.MockTransport(_keycloak),
                              upstream_transport=httpx.MockTransport(self.up.handler))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://proxy")

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_an_alt_route_reaches_its_own_url_with_the_fresh_token(self) -> None:
        r = await self.client.post("/alt/praxis/v1/chat/completions?x=1", json={"model": "auto"},
                                   headers={"Authorization": self.client.headers.get("Authorization", "Bearer dummy")})
        self.assertEqual(r.status_code, 200)
        sent = self.up.seen[-1]
        self.assertEqual(str(sent.url), "http://praxis.test:8080/v1/chat/completions?x=1")
        self.assertEqual(_headers(sent)["authorization"], "Bearer tok-1")
        self.assertEqual(json.loads(sent.content), {"model": "auto"})
        self.assertEqual(metrics.value("zuno_token_proxy_requests_total", upstream="alt-praxis", code="200"), 1)

    async def test_an_alt_route_keeps_a_path_prefix_of_its_url(self) -> None:
        await self.client.get("/alt/slow-one/v1/models")
        self.assertEqual(str(self.up.seen[-1].url), "https://slow.test/base/v1/models")

    async def test_the_entrys_fixed_headers_replace_the_clients_own_and_the_gateways_are_not_used(self) -> None:
        await self.client.get("/alt/praxis/v1/models", headers={"X-Zuno-Agent": "forged", "X-Alt": "forged", "X-Other": "kept"})
        sent = _headers(self.up.seen[-1])
        self.assertEqual((sent["x-zuno-agent"], sent["x-alt"], sent["x-other"]), ("kagent", "praxis", "kept"))
        # An entry without headers gets none: the ai-gateway's fixed headers are not lent to it by the proxy.
        await self.client.get("/alt/slow-one/v1/models", headers={"X-Zuno-Agent": "client"})
        self.assertEqual(_headers(self.up.seen[-1])["x-zuno-agent"], "client")

    async def test_an_unknown_name_is_404_and_nothing_is_relayed(self) -> None:
        r = await self.client.post("/alt/nope/v1/chat/completions", json={})
        self.assertEqual((r.status_code, r.json()), (404, {"error": "unknown alternative gateway"}))
        self.assertEqual(self.up.seen, [])
        self.assertEqual(metrics.value("zuno_token_proxy_requests_total", upstream="alt-unknown", code="404"), 1)

    async def test_only_v1_is_relayed_under_an_alt_name(self) -> None:
        self.assertEqual((await self.client.get("/alt/praxis/admin")).status_code, 404)
        self.assertEqual((await self.client.get("/alt/praxis/mcp")).status_code, 404)
        self.assertEqual(self.up.seen, [])

    async def test_the_zuno_routes_are_as_before(self) -> None:
        await self.client.get("/v1/models")
        self.assertEqual(str(self.up.seen[-1].url), "http://ai-gateway.test:8080/v1/models")
        await self.client.post("/mcp", json={})
        self.assertEqual(str(self.up.seen[-1].url), "http://mcp-gateway.test:8080/mcp")

    def test_timeouts_are_per_upstream(self) -> None:
        self.assertEqual(_timeout_for(ALT, "alt-slow-one", "POST").read, 45.0)
        self.assertEqual(_timeout_for(ALT, "alt-praxis", "POST").read, 300.0)
        self.assertEqual(_timeout_for(ALT, "ai-gateway", "POST").read, 300.0)
        self.assertEqual(_timeout_for(ALT, "mcp-gateway", "POST").read, 30.0)


class InboundAuthOnAltTests(AltRouteTests):
    """WP-225 lot C holds on the alternate routes too: relay() is the same."""
    settings = dataclasses.replace(ALT, inbound_keys=("k" * 32,))

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.client.headers["Authorization"] = "Bearer " + "k" * 32

    async def test_a_caller_without_the_key_is_401_on_an_alt_route(self) -> None:
        r = await self.client.get("/alt/praxis/v1/models", headers={"Authorization": "Bearer wrong"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.up.seen, [])


class EmptyListTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        metrics.reset()
        self.up = Upstreams()
        self.app = create_app(BASE, token_transport=httpx.MockTransport(_keycloak),
                              upstream_transport=httpx.MockTransport(self.up.handler))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://proxy")

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_without_alt_gateways_there_is_no_alt_route_at_all(self) -> None:
        self.assertEqual(BASE.alt_gateways, ())
        r = await self.client.post("/alt/praxis/v1/chat/completions", json={})
        self.assertEqual((r.status_code, r.json()), (404, {"detail": "Not Found"}))   # FastAPI's own: no such route
        self.assertEqual(self.up.seen, [])
        self.assertFalse(any(getattr(route, "path", "").startswith("/alt") for route in self.app.routes))
        self.assertEqual(metrics.render().count("alt-"), 0)

    async def test_without_alt_gateways_the_zuno_routes_are_relayed_as_before(self) -> None:
        await self.client.get("/v1/models", headers={"X-Zuno-Agent": "forged"})
        sent = self.up.seen[-1]
        self.assertEqual(str(sent.url), "http://ai-gateway.test:8080/v1/models")
        self.assertEqual((_headers(sent)["x-zuno-agent"], _headers(sent)["authorization"]), ("kagent", "Bearer tok-1"))


class CaBundleTests(unittest.TestCase):
    """An HTTPS alternative gateway is verified against CA_BUNDLE; the Zuno gateways' client is left as it was."""

    def _clients(self, settings: Settings) -> List[dict]:
        made: List[dict] = []
        real = httpx.AsyncClient

        class Spy(real):  # type: ignore[misc, valid-type]
            def __init__(self, *args, **kwargs):
                made.append(kwargs)
                super().__init__(*args, **kwargs)

        httpx.AsyncClient = Spy  # type: ignore[misc]
        try:
            create_app(settings)
        finally:
            httpx.AsyncClient = real  # type: ignore[misc]
        return made

    def test_the_alt_client_verifies_with_the_ca_bundle(self) -> None:
        made = self._clients(dataclasses.replace(ALT, ca_bundle=certifi.where()))
        self.assertEqual(len(made), 3)   # token, gateways, alternatives
        self.assertIsInstance(made[0]["verify"], ssl.SSLContext)
        self.assertNotIn("verify", made[1])
        self.assertIs(made[2]["verify"], made[0]["verify"])

    def test_no_alt_client_without_alt_gateways(self) -> None:
        made = self._clients(dataclasses.replace(BASE, ca_bundle=certifi.where()))
        self.assertEqual(len(made), 2)
        self.assertNotIn("verify", made[1])


class SettingsTests(unittest.TestCase):
    def test_unset_or_empty_means_none(self) -> None:
        self.assertEqual(Settings.from_env(ENV).alt_gateways, ())
        self.assertEqual(Settings.from_env({**ENV, "ALT_GATEWAYS": "  "}).alt_gateways, ())
        self.assertEqual(Settings.from_env({**ENV, "ALT_GATEWAYS": "[]"}).alt_gateways, ())

    def test_the_list_is_read(self) -> None:
        raw = json.dumps([{"name": "praxis", "url": "http://praxis.zuno-ai-gateways.svc:8080/v1/", "headers": {"X-A": "b"}},
                          {"name": "b2", "url": "https://b.example/v1", "timeout_s": 60}])
        got = Settings.from_env({**ENV, "ALT_GATEWAYS": raw}).alt_gateways
        self.assertEqual(got, (AltGateway("praxis", "http://praxis.zuno-ai-gateways.svc:8080/v1", {"X-A": "b"}, None),
                               AltGateway("b2", "https://b.example/v1", {}, 60.0)))

    def test_a_malformed_list_stops_the_proxy(self) -> None:
        bad = ['{"name": "a"}', '[1]', '[{"name": "A_b", "url": "http://x/v1"}]', '[{"name": "a", "url": "ftp://x"}]',
               '[{"name": "a", "url": "http://x/v1"}, {"name": "a", "url": "http://y/v1"}]',
               '[{"name": "a", "url": "http://x/v1", "headers": {"k": 1}}]', '[{"name": "a", "url": "http://x/v1", "timeout_s": 0}]',
               '[{"name": "a", "url": "http://x/v1", "token": "t"}]', '[{"name": "../v1", "url": "http://x/v1"}]']
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                Settings.from_env({**ENV, "ALT_GATEWAYS": raw})


if __name__ == "__main__":
    unittest.main()
