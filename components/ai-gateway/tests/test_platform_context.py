"""The quota class and project id are platform-side request context
(ADR-0511, ADR-0528): the gateway takes them from X-Zuno-Quota-Class and
X-Zuno-Project-Id only when the caller's token comes from a Keycloak client
listed in TRUSTED_PLATFORM_CLIENTS. Any other caller runs under the
`standard` class with no project, whatever it sent.

No network: providers are fakes. Run from this directory:

    python3 tests/test_platform_context.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unittest import mock  # noqa: E402

from app import main as app_main  # noqa: E402
from app.auth import CallerIdentity, validate_token  # noqa: E402
from test_wp157_maas_switches import _Env, _post  # noqa: E402

_HEADERS = {"X-Zuno-Quota-Class": "stresstest", "X-Zuno-Project-Id": "p-123"}


def _identity(azp):
    claims = {"azp": azp} if azp else {}
    return CallerIdentity(sub="bob", groups=["/sales"], raw_claims=claims, token="t")


def _context_seen(identity, headers, env=None):
    """Run one chat and return the (quota_class, project_id) the gateway used,
    as passed to the MaaS call context."""
    seen = {}
    real = app_main._maas_call_kwargs

    def spy(sub, groups, quota_class, project_id):
        seen["ctx"] = (quota_class, project_id)
        return real(sub, groups, quota_class, project_id)

    with _Env({}, env=env or {}), mock.patch.object(app_main, "_maas_call_kwargs", spy):
        app_main.app.dependency_overrides[validate_token] = lambda: identity
        r = _post(headers=headers)
    assert r.status_code == 200, r.text
    return seen["ctx"]


def test_untrusted_client_runs_standard_without_project() -> None:
    assert _context_seen(_identity("zuno-frontend"), _HEADERS) == ("standard", None)


def test_token_without_azp_is_untrusted() -> None:
    assert _context_seen(_identity(None), _HEADERS) == ("standard", None)


def test_trusted_platform_client_keeps_its_context() -> None:
    env = {"TRUSTED_PLATFORM_CLIENTS": "zuno-unifai-runtime,other"}
    assert _context_seen(_identity("zuno-unifai-runtime"), _HEADERS, env=env) == ("stresstest", "p-123")


def test_no_client_is_trusted_by_default() -> None:
    with mock.patch.dict(os.environ, {"TRUSTED_PLATFORM_CLIENTS": ""}):
        assert _identity("zuno-unifai-runtime").is_trusted_platform_client is False


def test_untrusted_unknown_class_is_not_denied() -> None:
    """An unknown class from an untrusted caller is dropped, not a 429."""
    assert _context_seen(_identity("zuno-frontend"), {"X-Zuno-Quota-Class": "no-such-class"}) == ("standard", None)


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except AssertionError as exc:
                failed += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failed else 0)
