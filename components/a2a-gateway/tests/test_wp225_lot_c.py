"""WP-225 lot C (ADR-0603 M14): the a2a-gateway signs the agent chain.

Each downstream call carries `X-Zuno-Agent-Chain` once AGENT_CHAIN_SIGNING_KEY_FILE
names a key: the agent served, its task, the delegators the executor checked, bound
to the caller's bearer and addressed to the receiving gateway. Without a key nothing
is added (today's headers). An inbound chain header is never passed on.

Run from the component directory:

    cd components/a2a-gateway && python3 tests/test_wp225_lot_c.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from app import auth, signed_chain  # noqa: E402
from test_a2a_gateway import USERS, GatewayTestCase  # noqa: E402

KEY = Ed25519PrivateKey.generate()
_DIR = tempfile.mkdtemp(prefix="wp225c-a2a-")
KEY_FILE = os.path.join(_DIR, "agent-chain.pem")
with open(KEY_FILE, "wb") as _fh:
    _fh.write(KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()))


def _verify(value: str, audience: str, token: str) -> signed_chain.VerifiedChain:
    return signed_chain.verify(value, public_key=KEY.public_key(), audience=audience, token=token)


class SignedChainTests(GatewayTestCase):
    async def test_without_a_key_no_chain_is_sent(self) -> None:
        with mock.patch.dict(os.environ, {"AGENT_CHAIN_SIGNING_KEY_FILE": ""}):
            await self.send("alpha", "tok-consultant")
        self.assertNotIn("x-zuno-agent-chain", self.down.llm_calls[0]["headers"])

    async def test_a_direct_call_is_signed_for_each_gateway(self) -> None:
        self.down.tools = [{"name": "search_confluence", "annotations": {"readOnlyHint": True}}]
        self.down.llm_script = [
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "search_confluence", "arguments": "{}"}}]},
            {"role": "assistant", "content": "done"},
        ]
        with mock.patch.dict(os.environ, {"AGENT_CHAIN_SIGNING_KEY_FILE": KEY_FILE}):
            await self.send("alpha", "tok-consultant")
        llm = self.down.llm_calls[0]["headers"]["x-zuno-agent-chain"]
        chain = _verify(llm, "ai-gateway", "tok-consultant")
        self.assertEqual((chain.agent, chain.task, chain.hops), ("alpha", "ask", ()))
        self.assertTrue(self.down.mcp_calls, "the tool loop reached the mcp-gateway")
        for call in self.down.mcp_calls:
            mcp = _verify(call["headers"]["x-zuno-agent-chain"], "mcp-gateway", "tok-consultant")
            self.assertEqual(mcp.agent, "alpha")
        with self.assertRaises(signed_chain.ChainSignatureError):
            _verify(llm, "mcp-gateway", "tok-consultant")  # addressed to the ai-gateway only
        with self.assertRaises(signed_chain.ChainSignatureError):
            _verify(llm, "ai-gateway", "tok-sales")  # bound to this caller's token

    async def test_a_checked_delegation_is_signed_with_its_hops(self) -> None:
        USERS["tok-both"] = auth.CallerIdentity("u-both", ["agent_alpha", "agent_beta"], {}, "tok-both")
        self.addCleanup(USERS.pop, "tok-both", None)
        headers = {"X-Zuno-Delegated-By": "alpha:ask", "X-Zuno-Delegation-Depth": "1"}
        with mock.patch.dict(os.environ, {"AGENT_CHAIN_SIGNING_KEY_FILE": KEY_FILE}):
            await self.send("beta", "tok-both", "delegated question", **headers)
        chain = _verify(self.down.llm_calls[0]["headers"]["x-zuno-agent-chain"], "ai-gateway", "tok-both")
        self.assertEqual((chain.agent, chain.task, chain.hops), ("beta", "ask", (("alpha", "ask"),)))

    async def test_an_inbound_chain_header_is_never_passed_on(self) -> None:
        forged = "eyJhbGciOiJub25lIn0.e30."
        with mock.patch.dict(os.environ, {"AGENT_CHAIN_SIGNING_KEY_FILE": ""}):
            await self.send("alpha", "tok-consultant", **{"X-Zuno-Agent-Chain": forged})
        self.assertNotIn("x-zuno-agent-chain", self.down.llm_calls[0]["headers"])

    async def test_an_unreadable_key_signs_nothing_and_the_turn_still_answers(self) -> None:
        with mock.patch.dict(os.environ, {"AGENT_CHAIN_SIGNING_KEY_FILE": "/nonexistent/key.pem"}):
            task = (await self.send("alpha", "tok-consultant")).root.result
        self.assertEqual(task.status.state.value, "completed")
        self.assertNotIn("x-zuno-agent-chain", self.down.llm_calls[0]["headers"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
