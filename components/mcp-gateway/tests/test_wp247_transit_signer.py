"""WP-247 (ADR-0602): the call assertion signed by Vault Transit instead of a key in the pod.

A fake Vault (a thread serving `auth/kubernetes/login` and `transit/sign/<key>`) holds a real Ed25519 key; the tests
check that what the gateway mints verifies like a file-signed assertion, that Vault problems fail the call (never a
fallback), and that the default (`file`) is untouched.

Run from the component directory:

    cd components/mcp-gateway && python3 tests/test_wp247_transit_signer.py
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("TOOL_BINDINGS_PATH", str(_REPO_ROOT / "platform/bindings/tools/tool-bindings.yaml"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import jwt  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from app import call_assertion  # noqa: E402

VAULT_KEY = Ed25519PrivateKey.generate()
VAULT_PUBLIC = VAULT_KEY.public_key()
LOCAL_KEY = Ed25519PrivateKey.generate()


class FakeVault:
    """Serves the two endpoints; `behaviour` lets a test break one of them."""

    def __init__(self) -> None:
        self.logins = 0
        self.signs = 0
        self.lease = 3600
        self.sign_status = 200
        self.sign_signature = None  # override the `signature` field
        self.login_status = 200
        self.revoke_first_token = False
        self.seen_tokens = []
        self.seen_roles = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def _answer(self, status, body):
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                if self.path == "/v1/auth/kubernetes/login":
                    outer.logins += 1
                    outer.seen_roles.append(body.get("role"))
                    if outer.login_status != 200:
                        return self._answer(outer.login_status, {"errors": ["denied"]})
                    return self._answer(200, {"auth": {"client_token": f"tok-{outer.logins}", "lease_duration": outer.lease}})
                if self.path == "/v1/transit/sign/mcp-call-assertion":
                    token = self.headers.get("X-Vault-Token")
                    outer.seen_tokens.append(token)
                    if outer.revoke_first_token and token == "tok-1":
                        return self._answer(403, {"errors": ["permission denied"]})
                    if outer.sign_status != 200:
                        return self._answer(outer.sign_status, {"errors": ["boom"]})
                    outer.signs += 1
                    signature = VAULT_KEY.sign(base64.b64decode(body["input"]))
                    value = outer.sign_signature if outer.sign_signature is not None else "vault:v1:" + base64.b64encode(signature).decode()
                    return self._answer(200, {"data": {"signature": value}})
                return self._answer(404, {"errors": ["not found"]})

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class TransitSignerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.vault = FakeVault()
        self.tmp = tempfile.TemporaryDirectory()
        sa = pathlib.Path(self.tmp.name) / "token"
        sa.write_text("sa-jwt\n")
        self.env = {
            "MCP_OUTBOUND_IDENTITY": "assertion",
            "MCP_CALL_ASSERTION_SIGNER": "transit",
            "VAULT_ADDR": self.vault.url,
            "VAULT_AUTH_ROLE": "mcp-gateway",
            "VAULT_TRANSIT_KEY": "mcp-call-assertion",
            "VAULT_SA_TOKEN_FILE": str(sa),
        }
        self._saved = {name: os.environ.get(name) for name in list(self.env) + ["MCP_CALL_ASSERTION_KEY_FILE"]}
        os.environ.update(self.env)
        os.environ.pop("MCP_CALL_ASSERTION_KEY_FILE", None)  # transit must not need the key file
        call_assertion._TRANSIT = call_assertion._VaultTransit()

    def tearDown(self) -> None:
        self.vault.close()
        self.tmp.cleanup()
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def _verify(self, token: str, audience: str = "aap") -> dict:
        return jwt.decode(token, VAULT_PUBLIC, algorithms=["EdDSA"], audience=audience, issuer="mcp-gateway")

    def test_assertion_signed_by_vault_verifies_like_a_file_signed_one(self) -> None:
        token = call_assertion.mint(audience="aap", sub="user-1", tool="launch", arguments={"b": 1, "a": "é"})
        claims = self._verify(token)
        self.assertEqual(jwt.get_unverified_header(token), {"typ": "zuno-call+jwt", "alg": "EdDSA"})
        self.assertEqual(claims["sub"], "user-1")
        self.assertEqual(claims["tool"], "launch")
        self.assertEqual(claims["args"], call_assertion.args_hash({"a": "é", "b": 1}))
        self.assertLessEqual(claims["exp"] - claims["iat"], call_assertion.MAX_TTL_SECONDS)
        self.assertEqual(self.vault.seen_roles, ["mcp-gateway"])

    def test_schema_read_assertion_has_no_tool_or_args(self) -> None:
        token = call_assertion.mint(audience="confluence", sub=call_assertion.SELF_SUBJECT, tool="")
        claims = self._verify(token, "confluence")
        self.assertEqual(claims["tool"], "")
        self.assertNotIn("args", claims)

    def test_one_login_serves_many_signatures(self) -> None:
        for _ in range(5):
            call_assertion.mint(audience="aap", sub="s", tool="t")
        self.assertEqual(self.vault.logins, 1)
        self.assertEqual(self.vault.signs, 5)

    def test_an_expiring_token_is_renewed(self) -> None:
        self.vault.lease = 10  # shorter than the 30 s margin: every signature logs in again
        call_assertion.mint(audience="aap", sub="s", tool="t")
        call_assertion.mint(audience="aap", sub="s", tool="t")
        self.assertEqual(self.vault.logins, 2)

    def test_a_revoked_token_is_replaced_once(self) -> None:
        self.vault.revoke_first_token = True
        token = call_assertion.mint(audience="aap", sub="s", tool="t")
        self._verify(token)
        self.assertEqual(self.vault.logins, 2)
        self.assertEqual(self.vault.seen_tokens, ["tok-1", "tok-2"])

    def test_vault_down_fails_the_call_without_fallback(self) -> None:
        self.vault.close()
        os.environ["MCP_CALL_ASSERTION_KEY_FILE"] = str(pathlib.Path(self.tmp.name) / "never-read")
        with self.assertRaises(call_assertion.AssertionUnavailable):
            call_assertion.mint(audience="aap", sub="s", tool="t")
        self.vault = FakeVault()  # tearDown closes it

    def test_login_refused_fails_the_call(self) -> None:
        self.vault.login_status = 403
        with self.assertRaises(call_assertion.AssertionUnavailable):
            call_assertion.mint(audience="aap", sub="s", tool="t")

    def test_sign_error_fails_the_call(self) -> None:
        self.vault.sign_status = 500
        with self.assertRaises(call_assertion.AssertionUnavailable):
            call_assertion.mint(audience="aap", sub="s", tool="t")

    def test_something_that_is_not_a_signature_is_refused(self) -> None:
        for bad in ("", "not-a-signature", "vault:v1:", "vault:v1:@@@", "vault:v1:" + base64.b64encode(b"short").decode()):
            self.vault.sign_signature = bad
            with self.assertRaises(call_assertion.AssertionUnavailable, msg=bad):
                call_assertion.mint(audience="aap", sub="s", tool="t")

    def test_missing_configuration_is_named(self) -> None:
        del os.environ["VAULT_ADDR"]
        with self.assertRaises(call_assertion.AssertionUnavailable) as caught:
            call_assertion.mint(audience="aap", sub="s", tool="t")
        self.assertIn("VAULT_ADDR", str(caught.exception))

    def test_unreadable_service_account_token_fails_the_call(self) -> None:
        os.environ["VAULT_SA_TOKEN_FILE"] = str(pathlib.Path(self.tmp.name) / "absent")
        with self.assertRaises(call_assertion.AssertionUnavailable):
            call_assertion.mint(audience="aap", sub="s", tool="t")

    def test_unknown_signer_fails_closed(self) -> None:
        os.environ["MCP_CALL_ASSERTION_SIGNER"] = "vault"
        with self.assertRaises(call_assertion.AssertionUnavailable):
            call_assertion.mint(audience="aap", sub="s", tool="t")

    def test_authorization_for_uses_the_transit_signer(self) -> None:
        binding = type("B", (), {"user_token": False, "gateway_token": True, "backend": "aap"})()
        header = call_assertion.authorization_for(binding, "caller-bearer", sub="u", tool="launch")
        self.assertTrue(header.startswith("Bearer "))
        self.assertNotIn("caller-bearer", header)
        self._verify(header.split(" ", 1)[1])
        self.assertEqual(self.vault.signs, 1)


class FileSignerUnchangedTest(unittest.TestCase):
    def test_default_signer_is_file_and_never_calls_vault(self) -> None:
        saved = os.environ.pop("MCP_CALL_ASSERTION_SIGNER", None)
        try:
            self.assertEqual(call_assertion.signer(), "file")
            token = call_assertion.mint(audience="aap", sub="s", tool="t", key=LOCAL_KEY)
            jwt.decode(token, LOCAL_KEY.public_key(), algorithms=["EdDSA"], audience="aap", issuer="mcp-gateway")
        finally:
            if saved is not None:
                os.environ["MCP_CALL_ASSERTION_SIGNER"] = saved

    def test_file_signer_still_reads_the_key_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "key.pem"
            path.write_bytes(LOCAL_KEY.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            saved = {n: os.environ.get(n) for n in ("MCP_CALL_ASSERTION_KEY_FILE", "MCP_CALL_ASSERTION_SIGNER")}
            os.environ["MCP_CALL_ASSERTION_KEY_FILE"] = str(path)
            os.environ.pop("MCP_CALL_ASSERTION_SIGNER", None)
            try:
                token = call_assertion.mint(audience="aap", sub="s", tool="t")
                jwt.decode(token, LOCAL_KEY.public_key(), algorithms=["EdDSA"], audience="aap", issuer="mcp-gateway")
            finally:
                for name, value in saved.items():
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
