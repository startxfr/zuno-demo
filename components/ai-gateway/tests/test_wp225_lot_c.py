"""WP-225 lot C (ADR-0603 M14) in the ai-gateway: the WP-209 classification floor
uses the agent of a verified `X-Zuno-Agent-Chain` (signed by the a2a-gateway,
app/signed_chain.py); a forged, expired, misaddressed or unbound chain is ignored
and the call keeps today's headers and floors. Also the per-client `azp`
allowlist (JWT_ALLOWED_CLIENTS).

Run from this directory:

    python3 tests/test_wp225_lot_c.py
"""
from __future__ import annotations

import os
import sys
import time
from types import SimpleNamespace
from unittest import mock

_TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_TESTS))
sys.path.insert(0, _TESTS)

import jwt  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import test_wp209_classification_floor as w209  # noqa: E402  (its _chat harness and floors)
from app import auth, signed_chain  # noqa: E402
from app import main as app_main  # noqa: E402
from app.auth import CallerIdentity  # noqa: E402

A2A_KEY = Ed25519PrivateKey.generate()
OTHER_KEY = Ed25519PrivateKey.generate()
PUBLIC = A2A_KEY.public_key().public_bytes(serialization.Encoding.PEM,
                                           serialization.PublicFormat.SubjectPublicKeyInfo).decode()
VERIFY = {"AGENT_CHAIN_VERIFY": "true", "AGENT_CHAIN_PUBLIC_KEY": PUBLIC}
# The w209 harness authenticates every call with token "t".
CLAIMS_TEKOS = {"X-Zuno-Data-Classification": "C1", "X-Zuno-Agent": "tekos",
                "X-Zuno-Task": "answer-technical-question"}


def _chain(agent="cognos", task="coming-soon", key=A2A_KEY, audience="ai-gateway", token="t", now=None):
    return signed_chain.sign(private_key=key, audience=audience, token=token, agent=agent, task=task, now=now)


def test_a_verified_chain_sets_the_floor_agent_over_a_low_floor_claim() -> None:
    """The WP-209 known gap: a caller claims tekos (C1 floor); the a2a-gateway attests cognos (C3)."""
    with mock.patch.object(app_main.logger, "warning"):
        resp, served, decisions, _ = w209._chat({**CLAIMS_TEKOS, "X-Zuno-Agent-Chain": _chain()}, env=VERIFY)
    assert resp.status_code == 200, resp.text
    assert served == ["local"], served
    assert decisions[-1]["classification"] == "C3"


def test_a_forged_chain_is_ignored_and_the_headers_apply_as_today() -> None:
    for value in (_chain(key=OTHER_KEY), _chain(audience="mcp-gateway"), _chain(token="someone-else"),
                  _chain(now=time.time() - 300), "garbage"):
        resp, served, decisions, _ = w209._chat({**CLAIMS_TEKOS, "X-Zuno-Agent-Chain": value}, env=VERIFY)
        assert resp.status_code == 200, resp.text
        assert decisions[-1]["classification"] == "C1", value
        assert served == ["openai"]


def test_without_verification_the_chain_header_is_ignored() -> None:
    resp, _, decisions, _ = w209._chat({**CLAIMS_TEKOS, "X-Zuno-Agent-Chain": _chain()},
                                       env={"AGENT_CHAIN_VERIFY": "", "AGENT_CHAIN_PUBLIC_KEY": PUBLIC})
    assert decisions[-1]["classification"] == "C1"


def test_no_chain_keeps_the_header_agent_and_its_floor() -> None:
    resp, served, decisions, _ = w209._chat(
        {"X-Zuno-Data-Classification": "C1", "X-Zuno-Agent": "cognos", "X-Zuno-Task": "coming-soon"}, env=VERIFY)
    assert decisions[-1]["classification"] == "C3"


def test_the_metered_paths_resolve_the_same_agent() -> None:
    identity = CallerIdentity(sub="u", groups=[], raw_claims={"azp": "unifai"}, token="t")
    with mock.patch.dict(os.environ, VERIFY):
        assert app_main._agent_identity(_chain(), "tekos", "answer-technical-question", identity) == \
            ("cognos", "coming-soon")
        assert app_main._agent_identity(_chain(key=OTHER_KEY), "tekos", "x", identity) == ("tekos", "x")
        assert app_main._agent_identity("", "tekos", "x", identity) == ("tekos", "x")


_RSA = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _token(**over) -> str:
    now = int(time.time())
    claims = {"sub": "u", "iss": auth.KEYCLOAK_ISSUER, "iat": now, "exp": now + 300, "groups": []}
    claims.update(over)
    return "Bearer " + jwt.encode(claims, _RSA, algorithm="RS256")


def _status(header, env) -> int:
    key = SimpleNamespace(key=_RSA.public_key())
    auth._jwks_client = SimpleNamespace(get_signing_key_from_jwt=lambda token: key)
    with mock.patch.dict(os.environ, env):
        try:
            auth.validate_token(header)
        except HTTPException as exc:
            return exc.status_code
    return 200


def test_the_allowed_clients_list_refuses_another_azp() -> None:
    assert _status(_token(azp="aap"), {"JWT_ALLOWED_CLIENTS": ""}) == 200
    env = {"JWT_ALLOWED_CLIENTS": "unifai, openclaw-*"}
    assert _status(_token(azp="unifai"), env) == 200
    assert _status(_token(azp="openclaw-consultant-02"), env) == 200
    assert _status(_token(azp="aap"), env) == 401
    assert _status(_token(), env) == 401


TESTS = [
    test_a_verified_chain_sets_the_floor_agent_over_a_low_floor_claim,
    test_a_forged_chain_is_ignored_and_the_headers_apply_as_today,
    test_without_verification_the_chain_header_is_ignored,
    test_no_chain_keeps_the_header_agent_and_its_floor,
    test_the_metered_paths_resolve_the_same_agent,
    test_the_allowed_clients_list_refuses_another_azp,
]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc!r}")
        else:
            print(f"PASS {test.__name__}")
    print(f"{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
