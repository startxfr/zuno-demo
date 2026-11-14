"""WP-250 lot 2: the generate_diagram handler calls diagram-render with a call assertion, not the shared token.

Run from the component directory:

    cd components/mcp-gateway && python3 tests/test_wp250_diagram_assertion.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import unittest
from unittest import mock

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("TOOL_BINDINGS_PATH", str(_REPO_ROOT / "platform/bindings/tools/tool-bindings.yaml"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from app import call_assertion  # noqa: E402
from app.handlers import diagram_gen  # noqa: E402

KEY = Ed25519PrivateKey.generate()


class _Response:
    def raise_for_status(self):
        pass

    def json(self):
        return {"data_base64": "PHN2Zy8+", "mime_type": "image/svg+xml"}


class DiagramAssertionTest(unittest.TestCase):
    def _handle(self):
        sent = {}

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, json=None, headers=None):
                sent.update(url=url, headers=headers or {})
                return _Response()

        real_mint = call_assertion.mint
        with mock.patch.object(diagram_gen.httpx, "AsyncClient", _Client), \
                mock.patch.object(call_assertion, "mint", lambda **kw: real_mint(key=KEY, **kw)):
            result = asyncio.run(diagram_gen.handle({"mermaid_source": "graph TD; A-->B"}, "ana"))
        return result, sent

    def test_the_render_call_carries_a_gateway_assertion_for_diagram_render(self):
        result, sent = self._handle()
        self.assertEqual(result["provider"], "mermaid-cli")
        self.assertNotIn("X-Zuno-Gateway-Token", sent["headers"])
        token = sent["headers"]["Authorization"].split(" ", 1)[1]
        claims = jwt.decode(token, KEY.public_key(), algorithms=["EdDSA"], audience="diagram-render", issuer="mcp-gateway")
        self.assertEqual((claims["sub"], claims["tool"], claims["act"]), ("ana", "render", {"sub": "mcp-gateway"}))

    def test_an_unusable_signer_fails_the_call_without_a_token_fallback(self):
        def broken(**_kw):
            raise call_assertion.AssertionUnavailable("no key")

        with mock.patch.object(call_assertion, "mint", broken):
            result = asyncio.run(diagram_gen.handle({"mermaid_source": "graph TD; A-->B"}, "ana"))
        self.assertIn("cannot sign", result["error"])


if __name__ == "__main__":
    unittest.main()
