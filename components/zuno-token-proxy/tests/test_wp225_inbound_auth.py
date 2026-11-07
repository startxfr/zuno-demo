"""WP-225 lot C (ADR-0602 clause 10): the token proxy authenticates its callers.

With INBOUND_KEYS_FILE set, a call without one of its keys is refused with 401 and
nothing reaches Keycloak or a gateway; a call with a key is relayed with the
client's own token, and the key is never forwarded. Unset, the proxy behaves as
before (any caller of the namespace, a dummy key replaced).

Run from the component directory:

    cd components/zuno-token-proxy && python3 tests/test_wp225_inbound_auth.py
"""
from __future__ import annotations

import dataclasses
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app import metrics  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from test_token_proxy import SETTINGS, FakeGateways, FakeKeycloak, _headers  # noqa: E402

KEY = "k" * 32
OTHER = "o" * 32


def _keys_file(text: str) -> str:
    handle = tempfile.NamedTemporaryFile("w", suffix=".keys", delete=False)
    handle.write(text)
    handle.close()
    return handle.name


class InboundAuthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        metrics.reset()
        self.kc = FakeKeycloak()
        self.gw = FakeGateways()
        settings = dataclasses.replace(SETTINGS, inbound_keys=(KEY, OTHER))
        self.app = create_app(settings, token_transport=httpx.MockTransport(self.kc.handler),
                              upstream_transport=httpx.MockTransport(self.gw.handler))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://proxy")

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_an_unauthenticated_call_is_refused_and_nothing_is_relayed(self) -> None:
        for headers in ({}, {"Authorization": "Bearer dummy"}, {"Authorization": f"Basic {KEY}"},
                        {"Authorization": f"Bearer {KEY[:-1]}"}, {"Authorization": "Bearer "}):
            for path in ("/v1/chat/completions", "/mcp"):
                response = await self.client.post(path, headers=headers, json={})
                self.assertEqual(response.status_code, 401, (path, headers))
        self.assertEqual(self.gw.seen, [])
        self.assertEqual(self.kc.calls, [], "no token is even fetched for an unauthenticated caller")
        self.assertEqual(metrics.value("zuno_token_proxy_requests_total", upstream="mcp-gateway", code="401"), 5)

    async def test_a_caller_with_a_key_is_relayed_with_the_clients_token_not_the_key(self) -> None:
        for key in (KEY, OTHER):
            response = await self.client.post("/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
                                              json={"model": "auto", "messages": []})
            self.assertEqual(response.status_code, 200)
        for seen in self.gw.seen:
            self.assertEqual(_headers(seen)["authorization"], "Bearer tok-1")
            self.assertNotIn(KEY, str(seen.headers))

    async def test_mcp_needs_the_key_too(self) -> None:
        response = await self.client.post("/mcp", headers={"Authorization": f"Bearer {KEY}"},
                                          json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(response.status_code, 200)

    async def test_health_and_metrics_stay_open(self) -> None:
        self.assertEqual((await self.client.get("/healthz")).status_code, 200)
        self.assertEqual((await self.client.get("/metrics")).status_code, 200)


class InboundKeysSettingsTests(unittest.TestCase):
    BASE = {"TOKEN_URL": "https://kc/token", "CLIENT_ID": "dify", "CLIENT_SECRET": "s"}

    def test_unset_means_no_inbound_check(self) -> None:
        self.assertEqual(Settings.from_env(self.BASE).inbound_keys, ())

    def test_keys_are_read_one_per_line(self) -> None:
        path = _keys_file(f"# dify api and knowledge adapter\n{KEY}\n\n{OTHER}\n")
        self.addCleanup(os.unlink, path)
        self.assertEqual(Settings.from_env({**self.BASE, "INBOUND_KEYS_FILE": path}).inbound_keys, (KEY, OTHER))

    def test_an_empty_missing_or_weak_file_refuses_to_start(self) -> None:
        for text in ("", "# only a comment\n", "short\n"):
            path = _keys_file(text)
            self.addCleanup(os.unlink, path)
            with self.assertRaises(ValueError):
                Settings.from_env({**self.BASE, "INBOUND_KEYS_FILE": path})
        with self.assertRaises(OSError):
            Settings.from_env({**self.BASE, "INBOUND_KEYS_FILE": "/nonexistent/keys"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
