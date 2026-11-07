"""WP-225 lot B (ADR-0603 M12): Salesforce owner scoping, from the signed caller context.

Run from this directory:

    python3 tests/test_wp225_owner_scoping.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import unittest.mock as mock

os.environ.setdefault("MCP_GATEWAY_WORKLOAD_TOKEN", "test-workload-token")
os.environ.setdefault("SALESFORCE_BASE_URL", "https://example.my.salesforce.com")
os.environ.setdefault("SALESFORCE_ACCESS_TOKEN", "test-access-token")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))

import httpx2  # noqa: E402
from httpx2 import ASGITransport  # noqa: E402
from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

import server  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "gateway_caller_context", os.path.join(REPO, "components", "mcp-gateway", "app", "caller_context.py")
)
caller_context = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(caller_context)

BASE_URL = "http://localhost:8000"
TOKEN = "test-workload-token"
AUD = "salesforce"  # this server's backend name
USER_ID = "005000000000001AAA"
OPP_ID = "006000000000001AAA"
ON = {"SALESFORCE_OWNER_SCOPING": "owner", "SALESFORCE_ALL_RECORDS_GROUPS": "sales-managers"}


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code, self._payload, self.text = status_code, payload, str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Fake:
    def __init__(self, responses):
        self.responses, self.requests = list(responses), []

    async def _do(self, method, path, **kwargs):
        self.requests.append((method, path, kwargs))
        return self.responses.pop(0)

    async def get(self, path, **kwargs):
        return await self._do("GET", path, **kwargs)

    async def post(self, path, **kwargs):
        return await self._do("POST", path, **kwargs)

    async def patch(self, path, **kwargs):
        return await self._do("PATCH", path, **kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


def _headers(tool, groups, email="seller@example.com", verified=True):
    h = {"X-Zuno-Gateway-Token": TOKEN}
    claims = {"email": email, "email_verified": verified}
    h.update(caller_context.build(audience=AUD, sub="u-1", groups=groups, claims=claims, tool=tool, workload_token=TOKEN))
    return h


async def _call(transport, headers, tool, args, fake, env):
    http_client = httpx2.AsyncClient(transport=transport, base_url=BASE_URL, headers=headers)
    with mock.patch.object(server, "_client", lambda: fake), mock.patch.dict(os.environ, env):
        async with streamable_http_client(f"{BASE_URL}/mcp", http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(tool, args)


def _text(result):
    return " ".join(getattr(b, "text", "") for b in result.content)


def _user_lookup(n=1):
    return _Resp(200, {"records": [{"Id": USER_ID}] * n})


async def test_off_behaves_as_before(transport):
    fake = _Fake([_Resp(200, {"records": []})])
    result = await _call(transport, {"X-Zuno-Gateway-Token": TOKEN}, "read_opportunity", {"query": "Acme"}, fake,
                         {"SALESFORCE_OWNER_SCOPING": "off"})
    assert not result.is_error, _text(result)
    assert "OwnerId" not in fake.requests[0][2]["params"]["q"]


async def test_read_is_limited_to_the_callers_records(transport):
    fake = _Fake([_user_lookup(), _Resp(200, {"records": []})])
    result = await _call(transport, _headers("read_opportunity", ["sales"]), "read_opportunity", {"query": "Acme"}, fake, ON)
    assert not result.is_error, _text(result)
    lookup, query = fake.requests[0][2]["params"]["q"], fake.requests[1][2]["params"]["q"]
    assert "FROM User WHERE Email = 'seller@example.com'" in lookup, lookup
    assert f"AND OwnerId = '{USER_ID}'" in query, query


async def test_all_records_group_is_not_scoped(transport):
    fake = _Fake([_Resp(200, {"records": []})])
    result = await _call(transport, _headers("read_opportunity", ["sales-managers"]), "read_opportunity",
                         {"query": "Acme"}, fake, ON)
    assert not result.is_error, _text(result)
    assert len(fake.requests) == 1 and "OwnerId" not in fake.requests[0][2]["params"]["q"]


async def test_no_verified_caller_is_refused(transport):
    fake = _Fake([])
    headers = {"X-Zuno-Gateway-Token": TOKEN, "X-Zuno-User-Email": "boss@example.com"}
    result = await _call(transport, headers, "read_opportunity", {"query": "Acme"}, fake, ON)
    assert result.is_error and fake.requests == [], _text(result)


async def test_an_unverified_email_is_refused_before_any_lookup(transport):
    """The realm does not verify emails and a user may edit their own: an email the
    token does not mark verified (false, absent, or a non-boolean) names nobody."""
    for verified in (False, None, "true"):
        fake = _Fake([])
        result = await _call(transport, _headers("read_opportunity", ["sales"], verified=verified),
                             "read_opportunity", {"query": "Acme"}, fake, ON)
        assert result.is_error and "verified email" in _text(result), (verified, _text(result))
        assert fake.requests == [], verified


async def test_a_context_signed_for_another_backend_is_refused(transport):
    fake = _Fake([])
    headers = {"X-Zuno-Gateway-Token": TOKEN}
    headers.update(caller_context.build(audience="confluence", sub="u-1", groups=["sales"],
                                        claims={"email": "seller@example.com", "email_verified": True},
                                        tool="read_opportunity", workload_token=TOKEN))
    result = await _call(transport, headers, "read_opportunity", {"query": "Acme"}, fake, ON)
    assert result.is_error and fake.requests == [], _text(result)


async def test_an_invalid_record_id_is_refused_even_with_scoping_off(transport):
    for bad in ("../../sobjects/User/005", "006000000000001AAA?x=1", "short"):
        fake = _Fake([])
        result = await _call(transport, {"X-Zuno-Gateway-Token": TOKEN}, "update_opportunity",
                             {"opportunity_id": bad, "stage": "Closed Won"}, fake, {"SALESFORCE_OWNER_SCOPING": "off"})
        assert result.is_error and fake.requests == [], bad


async def test_unknown_or_ambiguous_user_is_refused(transport):
    for n in (0, 2):
        fake = _Fake([_user_lookup(n)])
        result = await _call(transport, _headers("read_opportunity", ["sales"]), "read_opportunity",
                             {"query": "Acme"}, fake, ON)
        assert result.is_error and len(fake.requests) == 1, (n, _text(result))


async def test_an_email_cannot_break_out_of_the_soql_literal(transport):
    fake = _Fake([_user_lookup(0)])
    await _call(transport, _headers("read_opportunity", ["sales"], email="x' OR Email != '"),
                "read_opportunity", {"query": "Acme"}, fake, ON)
    assert "Email = 'x\\' or email != \\''" in fake.requests[0][2]["params"]["q"], fake.requests[0][2]["params"]["q"]


async def test_update_of_someone_elses_record_is_refused_before_the_write(transport):
    fake = _Fake([_user_lookup(), _Resp(200, {"records": []})])
    result = await _call(transport, _headers("update_opportunity", ["sales"]), "update_opportunity",
                         {"opportunity_id": OPP_ID, "stage": "Closed Won"}, fake, ON)
    assert result.is_error and "owned by the caller" in _text(result), _text(result)
    assert [r[0] for r in fake.requests] == ["GET", "GET"], "no PATCH may be sent"


async def test_update_of_an_owned_record_passes(transport):
    fake = _Fake([
        _user_lookup(),
        _Resp(200, {"records": [{"Id": OPP_ID}]}),
        _Resp(204, None),
        _Resp(200, {"Name": "Acme", "StageName": "Closed Won"}),
    ])
    result = await _call(transport, _headers("update_opportunity", ["sales"]), "update_opportunity",
                         {"opportunity_id": OPP_ID, "stage": "Closed Won"}, fake, ON)
    assert not result.is_error, _text(result)
    assert [r[0] for r in fake.requests] == ["GET", "GET", "PATCH", "GET"]


async def test_create_is_owned_by_the_caller(transport):
    fake = _Fake([_user_lookup(), _Resp(201, {"id": OPP_ID})])
    result = await _call(transport, _headers("create_opportunity", ["sales"]), "create_opportunity",
                         {"name": "Acme", "stage": "Prospecting", "close_date": "2026-12-31"}, fake, ON)
    assert not result.is_error, _text(result)
    assert fake.requests[1][2]["json"]["OwnerId"] == USER_ID


TESTS = [v for k, v in dict(globals()).items() if k.startswith("test_")]


async def _run_all() -> int:
    transport = ASGITransport(app=server.app)
    lifespan = server.app.router.lifespan_context(server.app)
    await lifespan.__aenter__()
    failures = 0
    try:
        for test in TESTS:
            try:
                await test(transport)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {test.__name__}: {exc!r}")
            else:
                print(f"PASS {test.__name__}")
    finally:
        await lifespan.__aexit__(None, None, None)
    return failures


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(_run_all()) else 0)
