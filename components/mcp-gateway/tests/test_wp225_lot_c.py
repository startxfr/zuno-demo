"""WP-225 lot C (ADR-0602 clause 10, ADR-0603 M14) in the mcp-gateway:

- the per-call assertion that replaces the forwarded bearer (app/call_assertion.py),
  per binding: the assertion for a Zuno server, nothing for a third-party backend,
  the bearer for a backend that needs the user's own token;
- one entitlement check for both front doors: a caller refused an agent on /mcp
  is refused on /v1/tools/{name}/invoke;
- the signed agent chain of the a2a-gateway (app/signed_chain.py): a valid chain
  sets the agent, a forged, expired, misaddressed or unbound one is ignored;
- the per-client `azp` allowlist (JWT_ALLOWED_CLIENTS);
- the copies of signed_chain.py are byte-identical in the three services.

Run from the component directory:

    cd components/mcp-gateway && python3 tests/test_wp225_lot_c.py
"""
from __future__ import annotations

import asyncio
import importlib
import logging
import os
import pathlib
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("TOOL_BINDINGS_PATH", str(_REPO_ROOT / "platform/bindings/tools/tool-bindings.yaml"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from okf_release_dir import AGENTS_DIR as _OKF_AGENTS_DIR, TOOL_POLICY_PATH as _OKF_TOOL_POLICY_PATH  # noqa: E402

os.environ.setdefault("TOOL_POLICY_PATH", _OKF_TOOL_POLICY_PATH)
os.environ.setdefault("DATA_CLASSIFICATION_PATH", str(_REPO_ROOT / "policies/data-classification/classification.yaml"))
os.environ.setdefault("AGENTS_DIR", _OKF_AGENTS_DIR)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import jwt  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.main as gateway_main  # noqa: E402
from app import auth, call_assertion, downstream, signed_chain  # noqa: E402
from app.auth import CallerIdentity, validate_token, validate_token_or_kubernetes  # noqa: E402
from app.bindings import Binding, _validate  # noqa: E402

AGENT, TASK = "tekos", "answer-technical-question"
GW_KEY = Ed25519PrivateKey.generate()
A2A_KEY = Ed25519PrivateKey.generate()
OTHER_KEY = Ed25519PrivateKey.generate()


def _pem_private(key) -> bytes:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def _pem_public(key) -> str:
    return key.public_key().public_bytes(serialization.Encoding.PEM,
                                         serialization.PublicFormat.SubjectPublicKeyInfo).decode()


_KEY_DIR = tempfile.mkdtemp(prefix="wp225c-")
GW_KEY_FILE = os.path.join(_KEY_DIR, "call-assertion.pem")
with open(GW_KEY_FILE, "wb") as _fh:
    _fh.write(_pem_private(GW_KEY))

CONSULTANT = CallerIdentity(sub="consultant-01", groups=["consultant", "agent_tekos"],
                            raw_claims={"iss": "zuno", "azp": "unifai"}, token="caller-jwt")
# Allowed confluence.page.search by the tool policy, but not entitled to the agent.
NOT_ENTITLED = CallerIdentity(sub="consultant-09", groups=["consultant"], raw_claims={"iss": "zuno"},
                              token="other-jwt")


class _Captured(Exception):
    pass


def _capture(binding_name: str, env: dict, schema: bool = False):
    """The outbound headers of a real downstream call (stopped before any I/O)."""
    captured = {}

    class _Client:
        def __init__(self, timeout=None, headers=None):
            captured.update(headers or {})

    def _stop(*_a, **_k):
        raise _Captured()

    binding = gateway_main.binding_registry.resolve(binding_name)
    with mock.patch.dict(os.environ, env), mock.patch.object(downstream, "MCP_GATEWAY_WORKLOAD_TOKEN", "wt"), \
            mock.patch.object(downstream.httpx2, "AsyncClient", _Client), \
            mock.patch.object(downstream, "streamable_http_client", _stop):
        try:
            if schema:
                asyncio.run(downstream._fetch_endpoint_schemas(binding.endpoint_url(), binding.gateway_token,
                                                               binding.backend))
            else:
                asyncio.run(downstream.invoke(binding, binding_name, {}, "consultant-01", "caller-jwt",
                                              caller_groups=["consultant"], caller_claims={}))
        except _Captured:
            pass
    return binding, captured


ASSERTION = {"MCP_OUTBOUND_IDENTITY": "assertion", "MCP_CALL_ASSERTION_KEY_FILE": GW_KEY_FILE}


def _decode_assertion(header: str, audience: str) -> dict:
    token = header.split(" ", 1)[1]
    assert jwt.get_unverified_header(token)["typ"] == call_assertion.TYPE
    return jwt.decode(token, GW_KEY.public_key(), algorithms=["EdDSA"], audience=audience, issuer="mcp-gateway")


class CallAssertionTest(unittest.TestCase):
    def test_default_mode_forwards_the_bearer_as_before(self):
        os.environ.pop("MCP_OUTBOUND_IDENTITY", None)
        self.assertEqual(call_assertion.mode(), "bearer")
        _, captured = _capture("confluence.page.search", {})
        self.assertEqual(captured["Authorization"], "Bearer caller-jwt")

    def test_a_malformed_mode_keeps_the_bearer(self):
        with mock.patch.dict(os.environ, {"MCP_OUTBOUND_IDENTITY": "exchange"}):
            self.assertEqual(call_assertion.mode(), "bearer")

    def test_a_zuno_server_gets_an_assertion_instead_of_the_bearer(self):
        binding, captured = _capture("confluence.page.search", ASSERTION)
        self.assertNotIn("caller-jwt", captured["Authorization"])
        claims = _decode_assertion(captured["Authorization"], "confluence")
        self.assertEqual((claims["sub"], claims["act"], claims["tool"]),
                         ("consultant-01", {"sub": "mcp-gateway"}, binding.provider_tool))
        self.assertLessEqual(claims["exp"] - claims["iat"], 60)
        self.assertTrue(claims["jti"])
        # Lot B's headers are unchanged.
        self.assertEqual(captured["X-Zuno-Gateway-Token"], "wt")
        self.assertIn("X-Zuno-Caller-Context", captured)

    def test_each_call_gets_its_own_jti(self):
        _, first = _capture("confluence.page.search", ASSERTION)
        _, second = _capture("confluence.page.search", ASSERTION)
        self.assertNotEqual(_decode_assertion(first["Authorization"], "confluence")["jti"],
                            _decode_assertion(second["Authorization"], "confluence")["jti"])

    def test_an_assertion_for_one_backend_does_not_verify_for_another(self):
        _, captured = _capture("confluence.page.search", ASSERTION)
        with self.assertRaises(jwt.InvalidAudienceError):
            _decode_assertion(captured["Authorization"], "git-forge")

    def test_a_third_party_backend_gets_no_identity_at_all(self):
        binding, captured = _capture("metrics.query", ASSERTION)
        self.assertEqual(binding.backend, "k8s")
        self.assertNotIn("Authorization", captured)
        self.assertNotIn("X-Zuno-Gateway-Token", captured)

    def test_a_binding_that_needs_the_user_token_keeps_it(self):
        binding = gateway_main.binding_registry.resolve("confluence.page.search")
        needing = Binding(**{**binding.__dict__, "user_token": True})
        with mock.patch.dict(os.environ, ASSERTION):
            self.assertEqual(call_assertion.authorization_for(needing, "caller-jwt", sub="s", tool="t"),
                             "Bearer caller-jwt")

    def test_no_shipped_binding_needs_the_user_token(self):
        self.assertEqual([b.capability for b in gateway_main.binding_registry._bindings if b.user_token], [])

    def test_a_non_boolean_user_token_fails_the_binding(self):
        binding = gateway_main.binding_registry.resolve("confluence.page.search")
        self.assertIn("user_token", _validate(Binding(**{**binding.__dict__, "user_token": "yes"})) or "")

    def test_a_missing_key_fails_the_call_and_never_falls_back_to_the_bearer(self):
        binding = gateway_main.binding_registry.resolve("confluence.page.search")
        env = {"MCP_OUTBOUND_IDENTITY": "assertion", "MCP_CALL_ASSERTION_KEY_FILE": "/nonexistent/key.pem"}
        with mock.patch.dict(os.environ, env):
            with self.assertRaises(downstream.DownstreamError) as ctx:
                asyncio.run(downstream.invoke(binding, "confluence.page.search", {}, "s", "caller-jwt"))
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertNotIn("caller-jwt", ctx.exception.message)

    def test_the_ttl_is_capped_at_sixty_seconds(self):
        with mock.patch.dict(os.environ, {"MCP_CALL_ASSERTION_TTL_SECONDS": "3600"}):
            self.assertEqual(call_assertion.ttl_seconds(), 60)
        with mock.patch.dict(os.environ, {"MCP_CALL_ASSERTION_TTL_SECONDS": "20"}):
            self.assertEqual(call_assertion.ttl_seconds(), 20)
        token = call_assertion.mint(audience="aap", sub="s", tool="t", key=GW_KEY, ttl=600)
        claims = jwt.decode(token, GW_KEY.public_key(), algorithms=["EdDSA"], audience="aap")
        self.assertEqual(claims["exp"] - claims["iat"], 60)

    def test_schema_reads_carry_a_gateway_assertion_without_a_tool(self):
        _, captured = _capture("confluence.page.search", ASSERTION, schema=True)
        claims = _decode_assertion(captured["Authorization"], "confluence")
        self.assertEqual((claims["sub"], claims["tool"]), (call_assertion.SELF_SUBJECT, ""))
        _, captured = _capture("confluence.page.search", {}, schema=True)
        self.assertNotIn("Authorization", captured, "bearer mode: schema reads unchanged")


def _invoke(identity, path_tool, headers, invoked):
    async def fake(*args, **kwargs):
        invoked.append((args, kwargs))
        return {"ok": True}

    gateway_main.app.dependency_overrides[validate_token] = lambda: identity
    gateway_main.app.dependency_overrides[validate_token_or_kubernetes] = lambda: identity
    try:
        with mock.patch.object(gateway_main, "invoke_downstream", fake):
            client = TestClient(gateway_main.app, raise_server_exceptions=False)
            rest = client.post(f"/v1/tools/{path_tool}/invoke", json={"query": "x"}, headers=headers)
            mcp = client.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": path_tool, "arguments": {"query": "x"}}})
        return rest, mcp
    finally:
        gateway_main.app.dependency_overrides.clear()


HEADERS = {"X-Zuno-Agent": AGENT, "X-Zuno-Task": TASK, "X-Zuno-Data-Classification": "C2"}


class RestEntitlementTest(unittest.TestCase):
    """With the switch on (chart restAgentEntitlement: true)."""

    def setUp(self):
        self._env = mock.patch.dict(os.environ, {"AGENT_ENTITLEMENT_EVERY_CALL": "true"})
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def test_a_caller_not_entitled_to_the_agent_is_refused_on_both_paths(self):
        invoked: list = []
        rest, mcp = _invoke(NOT_ENTITLED, "confluence.page.search", HEADERS, invoked)
        self.assertEqual(mcp.status_code, 403, mcp.text)
        self.assertEqual(rest.status_code, 403, rest.text)
        self.assertIn("not entitled to agent", rest.json()["detail"])
        self.assertEqual(invoked, [], "no backend was called")

    def test_an_entitled_caller_is_served_on_both_paths(self):
        invoked: list = []
        rest, mcp = _invoke(CONSULTANT, "confluence.page.search", HEADERS, invoked)
        self.assertEqual(rest.status_code, 200, rest.text)
        self.assertEqual(mcp.status_code, 200, mcp.text)
        self.assertFalse(mcp.json()["result"].get("isError"), mcp.text)
        self.assertEqual(len(invoked), 2)

    def test_a_tool_outside_the_task_is_refused_on_both_paths(self):
        invoked: list = []
        rest, mcp = _invoke(CONSULTANT, "confluence.page.create", HEADERS, invoked)
        self.assertEqual(rest.status_code, 403, rest.text)
        self.assertTrue(mcp.json()["result"]["isError"], mcp.text)
        self.assertEqual(invoked, [])

    def test_evaluate_is_the_one_entitlement_check(self):
        binding = gateway_main.binding_registry.resolve("confluence.page.search")
        decision = gateway_main.evaluate(
            store=gateway_main.policy_store, agents=gateway_main.agent_declarations,
            tool_name="confluence.page.search", agent_name=AGENT, task_name=TASK,
            caller_groups=NOT_ENTITLED.groups, request_classification="C2", equivalent_names=binding.all_names())
        self.assertFalse(decision.allowed)
        self.assertIn("ADR-0040", decision.reason)


def _chain(agent="cognos", task="answer", hops=(), token="caller-jwt", audience="mcp-gateway", key=A2A_KEY,
           now=None):
    return signed_chain.sign(private_key=key, audience=audience, token=token, agent=agent, task=task,
                             hops=hops, now=now)


VERIFY = {"AGENT_CHAIN_VERIFY": "true", "AGENT_CHAIN_PUBLIC_KEY": _pem_public(A2A_KEY)}


class SignedChainTest(unittest.TestCase):
    def _resolve(self, value, agent="tekos", task="answer-technical-question", env=VERIFY, token="caller-jwt",
                 audience="mcp-gateway"):
        with mock.patch.dict(os.environ, env):
            return signed_chain.resolve(value, agent, task, token=token, audience=audience)

    def test_a_valid_chain_sets_the_agent_and_a_disagreeing_header_is_logged(self):
        with self.assertLogs("zuno.signed_chain", level=logging.WARNING) as logs:
            resolved = self._resolve(_chain(hops=[("tekos", "answer-technical-question")]))
        self.assertTrue(resolved.verified)
        self.assertEqual((resolved.agent, resolved.task, resolved.hops),
                         ("cognos", "answer", (("tekos", "answer-technical-question"),)))
        self.assertIn("disagrees", "\n".join(logs.output))

    def test_a_forged_chain_is_ignored(self):
        resolved = self._resolve(_chain(key=OTHER_KEY))
        self.assertFalse(resolved.verified)
        self.assertEqual((resolved.agent, resolved.hops), ("tekos", None))

    def test_an_expired_chain_is_ignored(self):
        self.assertFalse(self._resolve(_chain(now=time.time() - 120)).verified)

    def test_a_chain_for_another_service_is_ignored(self):
        self.assertFalse(self._resolve(_chain(audience="ai-gateway")).verified)

    def test_a_chain_bound_to_another_token_is_ignored(self):
        self.assertFalse(self._resolve(_chain(token="someone-else-jwt")).verified)

    def test_a_tampered_chain_is_ignored(self):
        value = _chain()
        header, payload, sig = value.split(".")
        self.assertFalse(self._resolve(".".join([header, payload[:-2] + "AA", sig])).verified)
        self.assertFalse(self._resolve("not-a-jws").verified)

    def test_a_lifetime_above_sixty_seconds_is_ignored(self):
        now = int(time.time())
        claims = {"iss": "a2a-gateway", "aud": "mcp-gateway", "agent": "cognos", "task": "answer", "hops": [],
                  "ath": signed_chain.token_hash("caller-jwt"), "iat": now, "exp": now + 3600, "jti": "x"}
        value = jwt.encode(claims, A2A_KEY, algorithm="EdDSA", headers={"typ": signed_chain.TYPE})
        self.assertFalse(self._resolve(value).verified)

    def test_verification_off_ignores_the_header(self):
        resolved = self._resolve(_chain(), env={"AGENT_CHAIN_VERIFY": "", "AGENT_CHAIN_PUBLIC_KEY": ""})
        self.assertFalse(resolved.verified)
        self.assertEqual(resolved.agent, "tekos")

    def test_no_chain_keeps_todays_headers(self):
        resolved = self._resolve("")
        self.assertEqual((resolved.agent, resolved.task, resolved.verified), ("tekos", "answer-technical-question", False))

    def test_the_rest_path_uses_the_verified_agent(self):
        """A caller claims tekos in X-Zuno-Agent; the verified chain says it runs as
        another agent: the decision is the verified agent's."""
        seen = {}
        real = gateway_main.evaluate

        def spy(**kwargs):
            seen.update(agent=kwargs["agent_name"], task=kwargs["task_name"], chain=kwargs.get("chain"))
            return real(**kwargs)

        value = _chain(agent="tekos", task="answer-technical-question", hops=[])
        headers = {**HEADERS, "X-Zuno-Agent": "cognos", "X-Zuno-Agent-Chain": value}
        invoked: list = []
        with mock.patch.dict(os.environ, VERIFY), mock.patch.object(gateway_main, "evaluate", spy):
            rest, _ = _invoke(CONSULTANT, "confluence.page.search", headers, invoked)
        self.assertEqual(seen["agent"], "tekos")
        self.assertEqual(rest.status_code, 200, rest.text)

    def test_verified_hops_replace_the_delegation_headers(self):
        value = _chain(agent="tekos", task="answer-technical-question", hops=[("arkos", "draft")])
        with mock.patch.dict(os.environ, VERIFY):
            agent, task, chain = gateway_main._resolve_agent(value, "tekos", "answer-technical-question", "", "",
                                                             CONSULTANT)
        self.assertEqual((agent, task, chain.render()), ("tekos", "answer-technical-question", "arkos:draft"))
        # Unverified: the caller's headers, as before.
        agent, task, chain = gateway_main._resolve_agent("", "tekos", "t", "arkos:draft", "1", CONSULTANT)
        self.assertEqual((agent, chain.render()), ("tekos", "arkos:draft"))

    def test_the_copies_are_byte_identical(self):
        copies = {name: (_REPO_ROOT / "components" / name / "app" / "signed_chain.py").read_bytes()
                  for name in ("a2a-gateway", "ai-gateway", "mcp-gateway")}
        self.assertEqual(len(set(copies.values())), 1, "signed_chain.py differs between the three services")


_RSA = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _token(**over) -> str:
    now = int(time.time())
    claims = {"sub": "u", "iss": auth.KEYCLOAK_ISSUER, "iat": now, "exp": now + 300, "groups": []}
    claims.update(over)
    return "Bearer " + jwt.encode(claims, _RSA, algorithm="RS256")


class AllowedClientsTest(unittest.TestCase):
    def setUp(self):
        key = SimpleNamespace(key=_RSA.public_key())
        auth._jwks_client = SimpleNamespace(get_signing_key_from_jwt=lambda token: key)

    def _status(self, header, env):
        with mock.patch.dict(os.environ, env):
            try:
                validate_token(header)
            except HTTPException as exc:
                return exc.status_code
        return 200

    def test_empty_allows_every_client_as_before(self):
        self.assertEqual(self._status(_token(azp="anything"), {"JWT_ALLOWED_CLIENTS": ""}), 200)

    def test_a_client_outside_the_list_is_refused(self):
        env = {"JWT_ALLOWED_CLIENTS": "unifai,openclaw-*,dify"}
        self.assertEqual(self._status(_token(azp="unifai"), env), 200)
        self.assertEqual(self._status(_token(azp="openclaw-sale-01"), env), 200)
        self.assertEqual(self._status(_token(azp="dify"), env), 200)
        self.assertEqual(self._status(_token(azp="aap"), env), 401)
        self.assertEqual(self._status(_token(), env), 401, "a token without azp")


class RestEntitlementOffByDefaultTest(unittest.TestCase):
    """Default (switch off, the 2026-11-09 demo state): REST keeps today's behaviour,
    /mcp keeps its own up-front refusal."""

    def test_rest_serves_a_caller_not_entitled_to_the_agent_while_off(self):
        os.environ.pop("AGENT_ENTITLEMENT_EVERY_CALL", None)
        invoked: list = []
        rest, mcp = _invoke(NOT_ENTITLED, "confluence.page.search", HEADERS, invoked)
        self.assertEqual(rest.status_code, 200, rest.text)
        self.assertEqual(mcp.status_code, 403, mcp.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
