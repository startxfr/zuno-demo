"""WP-225 lot B (ADR-0603 M12): the Confluence space allowlist, from the signed caller context.

Exercised through the real MCP SDK client against this server's ASGI app. The caller's groups
come from the `ctx` claim of the gateway's signed call assertion (WP-250 lot 2; minted here with
test_support.assertion_headers, the shared workload token and HMAC headers are retired).

Run from this directory:

    python3 tests/test_wp225_space_allowlist.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import unittest.mock as mock

os.environ.setdefault("CONFLUENCE_BASE_URL", "https://example.atlassian.net")
os.environ.setdefault("CONFLUENCE_EMAIL", "technical@example.com")
os.environ.setdefault("CONFLUENCE_API_TOKEN", "test-token")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(HERE, "..", ".."))

import httpx2  # noqa: E402
from httpx2 import ASGITransport  # noqa: E402
from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

import server  # noqa: E402
from test_support.assertion_headers import headers_for  # noqa: E402

BASE_URL = "http://localhost:8000"
AUD = "confluence"  # this server's backend name
ALLOWLIST = json.dumps({"consultant": ["TECH", "OPS"], "ocp-paas-ops": ["*"]})


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

    async def put(self, path, **kwargs):
        return await self._do("PUT", path, **kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


def _page(page_id, space, title="Runbook"):
    return {"id": page_id, "title": title, "space": {"key": space}, "version": {"number": 1}, "_links": {}}


def _headers(tool, groups, **kwargs):
    return headers_for(AUD, tool, groups=groups, **kwargs)


async def _call(transport, headers, tool, args, fake):
    http_client = httpx2.AsyncClient(transport=transport, base_url=BASE_URL, headers=headers)
    with mock.patch.object(server, "_client", lambda: fake):
        async with streamable_http_client(f"{BASE_URL}/mcp", http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(tool, args)


async def _refused(transport, headers, tool, args, fake):
    """True when the call fails closed: the gateway-side 401 aborts the session (an exception in the
    client) or the tool answers is_error."""
    try:
        result = await _call(transport, headers, tool, args, fake)
    except BaseException as exc:  # noqa: BLE001 - ExceptionGroup from the SDK's task group
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return True
    return bool(result.is_error)


def _text(result):
    return " ".join(getattr(b, "text", "") for b in result.content)


async def test_no_allowlist_behaves_as_before(transport):
    for value in ("", "{}"):  # unset, and the chart default rendered as JSON
        fake = _Fake([_Resp(200, {"id": "1", **_page("1", "HR")})])
        with mock.patch.dict(os.environ, {"CONFLUENCE_SPACE_ALLOWLIST": value}):
            result = await _call(transport, headers_for(AUD, "read_page", groups=None), "read_page", {"page_id": "1"}, fake)
        assert not result.is_error, (value, _text(result))


async def test_create_in_an_allowed_space_passes(transport):
    fake = _Fake([_Resp(200, _page("9", "TECH"))])
    with mock.patch.dict(os.environ, {"CONFLUENCE_SPACE_ALLOWLIST": ALLOWLIST}):
        result = await _call(transport, _headers("create_page", ["consultant"]), "create_page",
                             {"space_key": "TECH", "title": "t", "body_html": "<p/>"}, fake)
    assert not result.is_error, _text(result)
    assert fake.requests and fake.requests[0][0] == "POST"


async def test_create_in_a_space_outside_the_callers_group_is_refused(transport):
    fake = _Fake([])
    with mock.patch.dict(os.environ, {"CONFLUENCE_SPACE_ALLOWLIST": ALLOWLIST}):
        result = await _call(transport, _headers("create_page", ["consultant"]), "create_page",
                             {"space_key": "HR", "title": "t", "body_html": "<p/>"}, fake)
    assert result.is_error and "outside the space allowlist" in _text(result), _text(result)
    assert fake.requests == [], "no Confluence call may be made"


async def test_create_under_a_parent_in_another_space_is_refused(transport):
    fake = _Fake([_Resp(200, _page("77", "HR"))])
    with mock.patch.dict(os.environ, {"CONFLUENCE_SPACE_ALLOWLIST": ALLOWLIST}):
        result = await _call(transport, _headers("create_page", ["consultant"]), "create_page",
                             {"space_key": "TECH", "title": "t", "body_html": "<p/>", "parent_id": "77"}, fake)
    assert result.is_error and "no Confluence page with id 77" in _text(result), _text(result)
    assert "HR" not in _text(result)
    assert [r[0] for r in fake.requests] == ["GET"], "no POST may be sent"


async def test_create_under_a_parent_of_another_allowed_space_is_refused(transport):
    fake = _Fake([_Resp(200, _page("78", "OPS"))])
    with mock.patch.dict(os.environ, {"CONFLUENCE_SPACE_ALLOWLIST": ALLOWLIST}):
        result = await _call(transport, _headers("create_page", ["consultant"]), "create_page",
                             {"space_key": "TECH", "title": "t", "body_html": "<p/>", "parent_id": "78"}, fake)
    assert result.is_error and [r[0] for r in fake.requests] == ["GET"], _text(result)


async def test_create_under_a_parent_in_the_same_space_passes(transport):
    fake = _Fake([_Resp(200, _page("79", "TECH")), _Resp(200, _page("80", "TECH"))])
    with mock.patch.dict(os.environ, {"CONFLUENCE_SPACE_ALLOWLIST": ALLOWLIST}):
        result = await _call(transport, _headers("create_page", ["consultant"]), "create_page",
                             {"space_key": "TECH", "title": "t", "body_html": "<p/>", "parent_id": "79"}, fake)
    assert not result.is_error, _text(result)
    assert [r[0] for r in fake.requests] == ["GET", "POST"]


async def test_update_reporting_another_space_after_the_write_is_logged(transport):
    fake = _Fake([_Resp(200, _page("5", "TECH")), _Resp(200, _page("5", "HR"))])
    with mock.patch.dict(os.environ, {"CONFLUENCE_SPACE_ALLOWLIST": ALLOWLIST}), \
            mock.patch.object(server.logger, "warning") as warned:
        result = await _call(transport, _headers("update_page", ["consultant"]), "update_page",
                             {"page_id": "5", "body_html": "<p/>"}, fake)
    assert not result.is_error, _text(result)
    assert warned.called and "after the write" in warned.call_args[0][0]


async def test_an_assertion_for_another_backend_or_expired_is_refused(transport):
    other = headers_for("git-forge", "create_page", groups=["ocp-paas-ops"])
    expired = headers_for(AUD, "create_page", groups=["ocp-paas-ops"], now=time.time() - 3600)
    with mock.patch.dict(os.environ, {"CONFLUENCE_SPACE_ALLOWLIST": ALLOWLIST}):
        for name, headers in (("other backend", other), ("expired", expired)):
            fake = _Fake([])
            refused = await _refused(transport, headers, "create_page",
                                     {"space_key": "HR", "title": "t", "body_html": "<p/>"}, fake)
            assert refused and fake.requests == [], name


async def test_wildcard_group_reaches_any_space(transport):
    fake = _Fake([_Resp(200, _page("9", "HR"))])
    with mock.patch.dict(os.environ, {"CONFLUENCE_SPACE_ALLOWLIST": ALLOWLIST}):
        result = await _call(transport, _headers("create_page", ["ocp-paas-ops"]), "create_page",
                             {"space_key": "HR", "title": "t", "body_html": "<p/>"}, fake)
    assert not result.is_error, _text(result)


async def test_update_of_a_page_in_another_space_is_refused_before_the_write(transport):
    fake = _Fake([_Resp(200, _page("5", "HR"))])
    with mock.patch.dict(os.environ, {"CONFLUENCE_SPACE_ALLOWLIST": ALLOWLIST}):
        result = await _call(transport, _headers("update_page", ["consultant"]), "update_page",
                             {"page_id": "5", "body_html": "<p/>"}, fake)
    assert result.is_error and "no Confluence page with id 5" in _text(result), _text(result)
    assert "HR" not in _text(result), "the refusal must not name the page's space"
    assert [r[0] for r in fake.requests] == ["GET"], "the PUT must never be sent"


async def test_read_of_a_page_in_another_space_returns_nothing(transport):
    fake = _Fake([_Resp(200, {**_page("5", "HR", title="Salaries"), "body": {"storage": {"value": "secret"}}})])
    with mock.patch.dict(os.environ, {"CONFLUENCE_SPACE_ALLOWLIST": ALLOWLIST}):
        result = await _call(transport, _headers("read_page", ["consultant"]), "read_page", {"page_id": "5"}, fake)
    assert result.is_error and "no Confluence page with id 5" in _text(result), _text(result)
    assert "secret" not in _text(result) and "Salaries" not in _text(result) and "HR" not in _text(result)


async def test_search_without_space_is_limited_to_the_callers_spaces(transport):
    payload = {"results": [_page("1", "TECH", "model serving"), _page("2", "HR", "model serving")]}
    fake = _Fake([_Resp(200, payload)])
    with mock.patch.dict(os.environ, {"CONFLUENCE_SPACE_ALLOWLIST": ALLOWLIST}):
        result = await _call(transport, _headers("search_pages", ["consultant"]), "search_pages",
                             {"query": "model serving"}, fake)
    assert not result.is_error, _text(result)
    out = result.structured_content["result"]
    assert [r["space"] for r in out["results"]] == ["TECH"], out
    assert 'space in ("OPS","TECH")' in fake.requests[0][2]["params"]["cql"]


async def test_search_in_a_named_space_outside_the_group_is_refused(transport):
    fake = _Fake([])
    with mock.patch.dict(os.environ, {"CONFLUENCE_SPACE_ALLOWLIST": ALLOWLIST}):
        result = await _call(transport, _headers("search_pages", ["consultant"]), "search_pages",
                             {"query": "pay", "space": "HR"}, fake)
    assert result.is_error and fake.requests == []


async def test_write_scope_leaves_reads_open(transport):
    fake = _Fake([_Resp(200, _page("5", "HR"))])
    env = {"CONFLUENCE_SPACE_ALLOWLIST": ALLOWLIST, "CONFLUENCE_SPACE_ALLOWLIST_SCOPE": "write"}
    with mock.patch.dict(os.environ, env):
        result = await _call(transport, headers_for(AUD, "read_page", groups=None), "read_page", {"page_id": "5"}, fake)
    assert not result.is_error, _text(result)


async def test_unsigned_or_forged_or_other_tool_context_is_refused(transport):
    """A caller cannot name its own groups: plain headers (X-Zuno-Groups, a client-sent
    X-Zuno-Assertion-Caller), an assertion signed with another key, an assertion without ctx
    and one minted for another tool all fail closed."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    spoof = headers_for(AUD, "create_page", groups=None)
    spoof["X-Zuno-Groups"] = "ocp-paas-ops"
    spoof["X-Zuno-Assertion-Caller"] = json.dumps({"groups": ["ocp-paas-ops"], "email": "u1@example.com"})
    forged = headers_for(AUD, "create_page", groups=["ocp-paas-ops"], key=Ed25519PrivateKey.generate())
    other_tool = _headers("search_pages", ["ocp-paas-ops"])
    no_ctx = headers_for(AUD, "create_page", groups=None)
    with mock.patch.dict(os.environ, {"CONFLUENCE_SPACE_ALLOWLIST": ALLOWLIST}):
        for name, headers in (("spoofed headers", spoof), ("forged signature", forged),
                              ("other tool", other_tool), ("no ctx", no_ctx)):
            fake = _Fake([])
            refused = await _refused(transport, headers, "create_page",
                                     {"space_key": "HR", "title": "t", "body_html": "<p/>"}, fake)
            assert refused, name
            assert fake.requests == [], name


async def test_malformed_allowlist_fails_closed(transport):
    fake = _Fake([])
    with mock.patch.dict(os.environ, {"CONFLUENCE_SPACE_ALLOWLIST": "{not json"}):
        result = await _call(transport, _headers("create_page", ["ocp-paas-ops"]), "create_page",
                             {"space_key": "TECH", "title": "t", "body_html": "<p/>"}, fake)
    assert result.is_error and fake.requests == []


async def test_ctx_is_not_in_the_published_schemas(transport):
    http_client = httpx2.AsyncClient(transport=transport, base_url=BASE_URL, headers=headers_for(AUD, ""))
    async with streamable_http_client(f"{BASE_URL}/mcp", http_client=http_client) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
    for tool in listed.tools:
        schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None)
        assert "ctx" not in (schema or {}).get("properties", {}), tool.name


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
