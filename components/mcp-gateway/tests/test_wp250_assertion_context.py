"""WP-250 lot 1: the gateway signs the caller context into the call assertion (`ctx`).

Run from the component directory:

    cd components/mcp-gateway && python3 tests/test_wp250_assertion_context.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import unittest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("TOOL_BINDINGS_PATH", str(_REPO_ROOT / "platform/bindings/tools/tool-bindings.yaml"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from app import call_assertion, caller_context  # noqa: E402

KEY = Ed25519PrivateKey.generate()
CLAIMS = {"email": "Ana@Example.com", "email_verified": True, "preferred_username": "ana", "sub": "ignored"}


class AssertionContextTest(unittest.TestCase):
    def _claims(self, token):
        return jwt.decode(token, KEY.public_key(), algorithms=["EdDSA"], audience="confluence", issuer="mcp-gateway")

    def test_context_fields_come_from_the_validated_identity_only(self):
        ctx = caller_context.assertion_context(groups=["b", "a", "a", ""], claims=CLAIMS)
        self.assertEqual(ctx, {"groups": ["a", "b"], "email": "ana@example.com",
                               "email_verified": True, "username": "ana"})

    def test_an_unverified_email_is_not_verified(self):
        ctx = caller_context.assertion_context(groups=[], claims={"email": "x@y", "email_verified": "true"})
        self.assertFalse(ctx["email_verified"])

    def test_no_identity_gives_an_empty_context(self):
        self.assertEqual(caller_context.assertion_context(groups=None, claims=None),
                         {"groups": [], "email": "", "email_verified": False, "username": ""})

    def test_the_assertion_carries_ctx_when_given(self):
        ctx = caller_context.assertion_context(groups=["g"], claims=CLAIMS)
        claims = self._claims(call_assertion.mint(audience="confluence", sub="s", tool="t", key=KEY, caller=ctx))
        self.assertEqual(claims["ctx"], ctx)
        self.assertEqual(claims["tool"], "t")

    def test_no_ctx_without_a_caller(self):
        self.assertNotIn("ctx", self._claims(call_assertion.mint(audience="confluence", sub="s", tool="t", key=KEY)))

    def test_a_schema_read_assertion_never_carries_ctx(self):
        ctx = caller_context.assertion_context(groups=["g"], claims=CLAIMS)
        token = call_assertion.mint(audience="confluence", sub="s", tool="", key=KEY, caller=ctx)
        self.assertNotIn("ctx", self._claims(token))

    def test_authorization_for_passes_the_caller_through(self):
        os.environ["MCP_OUTBOUND_IDENTITY"] = "assertion"
        self.addCleanup(os.environ.pop, "MCP_OUTBOUND_IDENTITY", None)
        binding = type("B", (), {"user_token": False, "gateway_token": True, "backend": "confluence"})()
        ctx = caller_context.assertion_context(groups=["g"], claims=CLAIMS)
        orig = call_assertion.signing_key
        call_assertion.signing_key = lambda: KEY
        self.addCleanup(setattr, call_assertion, "signing_key", orig)
        header = call_assertion.authorization_for(binding, "bearer", sub="s", tool="t", caller=ctx)
        self.assertEqual(self._claims(header.split(" ", 1)[1])["ctx"], ctx)


if __name__ == "__main__":
    unittest.main()
