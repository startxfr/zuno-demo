#!/usr/bin/env python3
"""Offline JWT validation tests for the MCP Gateway's auth.py (ADR-0053
"missing/expired tokens" mandatory security-negative case).

Structurally identical to components/agent-runtime/tests/test_auth.py -
app/auth.py itself is a deliberate per-service duplicate (see that
module's own docstring), so this is the mcp-gateway half of the same
mandatory negative case, not new coverage of new logic.

Run directly:

    cd components/mcp-gateway && python3 tests/test_auth.py
"""
from __future__ import annotations

import pathlib
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

from app import auth  # noqa: E402

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_ISSUER = auth.KEYCLOAK_ISSUER


def _install_fake_jwks() -> None:
    fake_signing_key = SimpleNamespace(key=_PRIVATE_KEY.public_key())
    auth._jwks_client = SimpleNamespace(get_signing_key_from_jwt=lambda token: fake_signing_key)


def _make_token(**claim_overrides) -> str:
    now = int(time.time())
    claims = {
        "sub": "test-user",
        "iss": _ISSUER,
        "iat": now,
        "exp": now + 300,
        "groups": ["/consultant"],
    }
    claims.update(claim_overrides)
    return jwt.encode(claims, _PRIVATE_KEY, algorithm="RS256")


def test_valid_token_is_accepted() -> None:
    _install_fake_jwks()
    identity = auth.validate_token(authorization=f"Bearer {_make_token()}")
    assert identity.sub == "test-user"
    assert identity.groups == ["consultant"]


def test_expired_token_is_rejected() -> None:
    """An otherwise-valid, correctly-signed token whose `exp` has already
    passed must be rejected with 401, not silently accepted - PyJWT's own
    default `exp` verification (auth.py never sets `verify_exp: False`).
    """
    _install_fake_jwks()
    now = int(time.time())
    token = _make_token(iat=now - 600, exp=now - 300)
    try:
        auth.validate_token(authorization=f"Bearer {token}")
        raise AssertionError("expected an HTTPException for an expired token")
    except AssertionError:
        raise
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 401, f"expected 401, got {exc!r}"


def test_token_signed_by_an_untrusted_key_is_rejected() -> None:
    """A well-formed token signed by a key other than the one the (fake)
    JWKS endpoint vouches for must be rejected - proves signature
    verification is real, not skipped.
    """
    _install_fake_jwks()
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    forged = jwt.encode(
        {"sub": "test-user", "iss": _ISSUER, "iat": now, "exp": now + 300, "groups": []},
        other_key,
        algorithm="RS256",
    )
    try:
        auth.validate_token(authorization=f"Bearer {forged}")
        raise AssertionError("expected an HTTPException for a token signed by an untrusted key")
    except AssertionError:
        raise
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 401, f"expected 401, got {exc!r}"


def test_missing_authorization_header_is_rejected() -> None:
    try:
        auth.validate_token(authorization=None)
        raise AssertionError("expected an HTTPException for a missing Authorization header")
    except AssertionError:
        raise
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 401, f"expected 401, got {exc!r}"


TESTS = [
    test_valid_token_is_accepted,
    test_expired_token_is_rejected,
    test_token_signed_by_an_untrusted_key_is_rejected,
    test_missing_authorization_header_is_rejected,
]


def main() -> int:
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
