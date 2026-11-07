#!/usr/bin/env python3
"""WP-222 / ADR-0602: audience enforcement is switchable and fails closed, and
/admin/* needs a token whose groups include an admin group.

Run from this directory:

    python3 tests/test_wp222_audience_and_admin.py
"""
from __future__ import annotations

import importlib
import os
import pathlib
import sys
import time
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app import auth  # noqa: E402

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _install_jwks() -> None:
    key = SimpleNamespace(key=_KEY.public_key())
    auth._jwks_client = SimpleNamespace(get_signing_key_from_jwt=lambda token: key)


def _token(**over) -> str:
    now = int(time.time())
    claims = {"sub": "u", "iss": auth.KEYCLOAK_ISSUER, "iat": now, "exp": now + 300, "groups": []}
    claims.update(over)
    return "Bearer " + jwt.encode(claims, _KEY, algorithm="RS256")


def _status(fn, *args) -> int:
    try:
        fn(*args)
    except HTTPException as exc:
        return exc.status_code
    return 200


def test_required_flag_without_audience_refuses_to_start() -> None:
    with mock.patch.dict(os.environ, {"JWT_AUDIENCE_REQUIRED": "true", "JWT_AUDIENCE": ""}):
        try:
            importlib.reload(auth)
        except RuntimeError:
            return
        raise AssertionError("module imported with JWT_AUDIENCE_REQUIRED and no audience")


def test_audience_mismatch_is_refused_once_set() -> None:
    with mock.patch.dict(os.environ, {"JWT_AUDIENCE": "zuno-gw", "JWT_AUDIENCE_REQUIRED": "true"}):
        importlib.reload(auth)
        _install_jwks()
        assert _status(auth.validate_token, _token(aud="openshift")) == 401
        assert _status(auth.validate_token, _token(aud="zuno-gw")) == 200
    importlib.reload(auth)


def test_admin_requires_an_admin_group() -> None:
    _install_jwks()
    assert _status(auth.require_admin, None) == 401
    assert _status(auth.require_admin, _token(groups=["/consultant"])) == 403
    assert _status(auth.require_admin, _token(groups=["/ocp-paas-ops"])) == 200


def test_admin_mode_off_is_an_explicit_opt_out() -> None:
    with mock.patch.dict(os.environ, {"ADMIN_AUTH_MODE": "off"}):
        assert _status(auth.require_admin, None) == 200


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
