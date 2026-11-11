"""WP-247 lot 2 (ADR-0602): the agent chain signed by Vault Transit instead of a key in the pod.

A fake Vault (a thread serving `auth/kubernetes/login` and `transit/sign/agent-chain`) holds a real
Ed25519 key. The tests check that the chain the gateway sends verifies like a file-signed one, that a
Vault problem sends NO chain (never a fallback to a local key), and that the default is untouched.

Run from the component directory:

    cd components/a2a-gateway && python3 tests/test_wp247_transit_chain.py
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from app import clients, signed_chain, transit_signer  # noqa: E402

VAULT_KEY = Ed25519PrivateKey.generate()
LOCAL_KEY = Ed25519PrivateKey.generate()
TOKEN = "caller-bearer"


class FakeVault:
    def __init__(self) -> None:
        self.logins = 0
        self.signs = 0
        self.sign_status = 200
        self.sign_signature = None
        self.login_status = 200
        self.seen_roles = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
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
                    return self._answer(200, {"auth": {"client_token": f"tok-{outer.logins}", "lease_duration": 3600}})
                if self.path == "/v1/transit/sign/agent-chain":
                    if outer.sign_status != 200:
                        return self._answer(outer.sign_status, {"errors": ["boom"]})
                    outer.signs += 1
                    signature = VAULT_KEY.sign(base64.b64decode(body["input"]))
                    value = outer.sign_signature if outer.sign_signature is not None \
                        else "vault:v1:" + base64.b64encode(signature).decode()
                    return self._answer(200, {"data": {"signature": value}})
                return self._answer(404, {"errors": ["not found"]})

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class TransitChainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.vault = FakeVault()
        self.tmp = tempfile.TemporaryDirectory()
        sa = pathlib.Path(self.tmp.name) / "token"
        sa.write_text("sa-jwt\n")
        env = {
            "AGENT_CHAIN_SIGNER": "transit",
            "VAULT_ADDR": self.vault.url,
            "VAULT_AUTH_ROLE": "a2a-gateway",
            "VAULT_TRANSIT_KEY": "agent-chain",
            "VAULT_SA_TOKEN_FILE": str(sa),
        }
        self._saved = {n: os.environ.get(n) for n in list(env) + ["AGENT_CHAIN_SIGNING_KEY_FILE"]}
        os.environ.update(env)
        os.environ.pop("AGENT_CHAIN_SIGNING_KEY_FILE", None)
        transit_signer._TRANSIT = transit_signer.VaultTransit()

    def tearDown(self) -> None:
        self.vault.close()
        self.tmp.cleanup()
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def _headers(self, audience: str = "mcp-gateway", delegated: str = "") -> dict:
        extra = {"X-Zuno-Delegated-By": delegated} if delegated else {}
        return clients._downstream_headers(TOKEN, "tekos", "chat", "C1", "run-1", extra, audience)

    def _verify(self, value: str, audience: str = "mcp-gateway"):
        return signed_chain.verify(value, public_key=VAULT_KEY.public_key(), audience=audience, token=TOKEN)

    def test_chain_signed_by_vault_verifies_like_a_file_signed_one(self) -> None:
        chain = self._verify(self._headers()[signed_chain.HEADER])
        self.assertEqual((chain.agent, chain.task, chain.hops), ("tekos", "chat", ()))
        self.assertEqual(self.vault.seen_roles, ["a2a-gateway"])

    def test_delegators_are_signed(self) -> None:
        chain = self._verify(self._headers(delegated="arkos:review")[signed_chain.HEADER])
        self.assertEqual(chain.hops, (("arkos", "review"),))

    def test_header_matches_what_pyjwt_would_write(self) -> None:
        import jwt
        value = self._headers()[signed_chain.HEADER]
        self.assertEqual(jwt.get_unverified_header(value), {"typ": signed_chain.TYPE, "alg": "EdDSA"})

    def test_a_chain_for_another_audience_or_token_is_refused(self) -> None:
        value = self._headers("ai-gateway")[signed_chain.HEADER]
        with self.assertRaises(signed_chain.ChainSignatureError):
            self._verify(value, "mcp-gateway")
        with self.assertRaises(signed_chain.ChainSignatureError):
            signed_chain.verify(value, public_key=VAULT_KEY.public_key(), audience="ai-gateway", token="other")

    def test_vault_down_sends_no_chain_and_no_fallback(self) -> None:
        self.vault.close()
        # a usable local key must NOT be picked up as a fallback
        path = pathlib.Path(self.tmp.name) / "key.pem"
        path.write_bytes(LOCAL_KEY.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        os.environ["AGENT_CHAIN_SIGNING_KEY_FILE"] = str(path)
        headers = self._headers()
        self.assertNotIn(signed_chain.HEADER, headers)
        self.assertEqual(headers["Authorization"], f"Bearer {TOKEN}")
        self.vault = FakeVault()

    def test_login_refused_sends_no_chain(self) -> None:
        self.vault.login_status = 403
        self.assertNotIn(signed_chain.HEADER, self._headers())

    def test_sign_error_sends_no_chain(self) -> None:
        self.vault.sign_status = 500
        self.assertNotIn(signed_chain.HEADER, self._headers())

    def test_something_that_is_not_a_signature_sends_no_chain(self) -> None:
        for bad in ("", "nope", "vault:v1:", "vault:v1:@@@", "vault:v1:" + base64.b64encode(b"short").decode()):
            self.vault.sign_signature = bad
            self.assertNotIn(signed_chain.HEADER, self._headers(), msg=bad)

    def test_missing_configuration_sends_no_chain(self) -> None:
        del os.environ["VAULT_ADDR"]
        self.assertNotIn(signed_chain.HEADER, self._headers())

    def test_unknown_signer_sends_no_chain(self) -> None:
        os.environ["AGENT_CHAIN_SIGNER"] = "vault"
        self.assertNotIn(signed_chain.HEADER, self._headers())

    def test_one_login_serves_many_signatures(self) -> None:
        for _ in range(4):
            self._headers()
        self.assertEqual((self.vault.logins, self.vault.signs), (1, 4))

    def test_sign_without_key_or_signer_is_refused(self) -> None:
        with self.assertRaises(signed_chain.ChainSignatureError):
            signed_chain.sign(audience="mcp-gateway", token=TOKEN, agent="tekos", task="chat")


class FileSignerUnchangedTest(unittest.TestCase):
    def test_default_signer_is_file_and_never_calls_vault(self) -> None:
        saved = {n: os.environ.pop(n, None) for n in ("AGENT_CHAIN_SIGNER", "AGENT_CHAIN_SIGNING_KEY_FILE")}
        try:
            self.assertEqual(transit_signer.signer(), "file")
            # no key file: nothing is signed, as before
            self.assertNotIn(signed_chain.HEADER,
                             clients._downstream_headers(TOKEN, "tekos", "chat", "C1", "r", {}, "mcp-gateway"))
        finally:
            for n, v in saved.items():
                if v is not None:
                    os.environ[n] = v

    def test_file_signer_still_signs_with_the_key_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "key.pem"
            path.write_bytes(LOCAL_KEY.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            saved = {n: os.environ.get(n) for n in ("AGENT_CHAIN_SIGNER", "AGENT_CHAIN_SIGNING_KEY_FILE")}
            os.environ.pop("AGENT_CHAIN_SIGNER", None)
            os.environ["AGENT_CHAIN_SIGNING_KEY_FILE"] = str(path)
            try:
                headers = clients._downstream_headers(TOKEN, "tekos", "chat", "C1", "r", {}, "mcp-gateway")
                signed_chain.verify(headers[signed_chain.HEADER], public_key=LOCAL_KEY.public_key(),
                                    audience="mcp-gateway", token=TOKEN)
            finally:
                for n, v in saved.items():
                    if v is None:
                        os.environ.pop(n, None)
                    else:
                        os.environ[n] = v


if __name__ == "__main__":
    unittest.main()
