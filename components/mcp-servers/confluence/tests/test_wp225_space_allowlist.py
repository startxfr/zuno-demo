"""WP-225 lot B (ADR-0603 M12): the Confluence space allowlist, from the signed caller context.

Exercised through the real MCP SDK client against this server's ASGI app, with the
caller context signed by the gateway's own module (components/mcp-gateway/app/
caller_context.py), so the signer and this server's verifier are tested together.

Run from this directory:

    python3 tests/test_wp225_space_allowlist.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import time
import unittest.mock as mock

os.environ.setdefault("MCP_GATEWAY_WORKLOAD_TOKEN", "test-workload-token")
os.environ.setdefault("CONFLUENCE_BASE_URL", "https://example.atlassian.net")
os.environ.setdefault("CONFLUENCE_EMAIL", "technical@example.com")
os.environ.setdefault("CONFLUENCE_API_TOKEN", "test-token")

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


def _headers(tool, groups, *, token=TOKEN, iat=None):
    h = {"X-Zuno-Gateway-Token": TOKEN}
    h.update(caller_context.build(sub="u-1", groups=groups, claims={"email": "u1@example.com"},
                                  tool=tool, workload_token=token, now=iat))
    return h


async def _call(transport, headers, tool, args, fake):
    http_client = httpx2.AsyncClient(transport=transport, base_url=BASE_URL, headers=headers)
    with mock.patch.object(server, "_client", lambda: fake):
        async with streamable_http_client(f"{BASE_URL}/mcp", http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(tool, args)


def _text(result):
    return " ".join(getattr(b, "text", "") for b in result.content)


async def test_no_allowlist_behaves_as_before(transport):
    for value in ("", "{}"):  # unset, and the chart default rendered as JSON
        fake = _Fake([_Resp(200, {"id": "1", **_page("1", "HR")})])
        with mock.patch.dict(os.environ, {"CONFLUENCE_SPACE_ALLOWLIST": value}):
            result = await _call(transport, {"X-Zuno-Gateway-Token": TOKEN}, "read_page", {"page_id": "1"}, fake)
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
    assert result.is_error and "HR" in _text(result), _text(result)
    assert [r[0] for r in fake.requests] == ["GET"], "the PUT must never be sent"


async def test_read_of_a_page_in_another_space_returns_nothing(transport):
    fake = _Fake([_Resp(200, {**_page("5", "HR", title="Salaries"), "body": {"storage": {"value": "secret"}}})])
    with mock.patch.dict(os.environ, {"CONFLUENCE_SPACE_ALLOWLIST": ALLOWLIST}):
        result = await _call(transport, _headers("read_page", ["consultant"]), "read_page", {"page_id": "5"}, fake)
    assert result.is_error, _text(result)
    assert "secret" not in _text(result) and "Salaries" not in _text(result)


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
        result = await _call(transport, {"X-Zuno-Gateway-Token": TOKEN}, "read_page", {"page_id": "5"}, fake)
    assert not result.is_error, _text(result)


async def test_unsigned_or_forged_or_stale_or_other_tool_context_is_refused(transport):
    """A caller cannot name its own groups: a plain header, a context signed with
    another key, an old one and one minted for another tool all fail closed."""
    plain = {"X-Zuno-Gateway-Token": TOKEN, "X-Zuno-Groups": "ocp-paas-ops"}
    forged = _headers("create_page", ["ocp-paas-ops"], token="not-the-workload-token")
    forged["X-Zuno-Gateway-Token"] = TOKEN
    stale = _headers("create_page", ["ocp-paas-ops"], iat=time.time() - 3600)
    other_tool = _headers("search_pages", ["ocp-paas-ops"])
    tampered = _headers("create_page", ["consultant"])
    tampered["X-Zuno-Caller-Context"] = caller_context.build(
        sub="u-1", groups=["ocp-paas-ops"], claims={}, tool="create_page", workload_token=TOKEN
    )["X-Zuno-Caller-Context"]
    tampered["X-Zuno-Caller-Signature"] = "0" * 64
    with mock.patch.dict(os.environ, {"CONFLUENCE_SPACE_ALLOWLIST": ALLOWLIST}):
        for name, headers in (("plain", plain), ("forged", forged), ("stale", stale),
                              ("other tool", other_tool), ("tampered", tampered)):
            fake = _Fake([])
            result = await _call(transport, headers, "create_page",
                                 {"space_key": "HR", "title": "t", "body_html": "<p/>"}, fake)
            assert result.is_error, name
            assert fake.requests == [], name


async def test_malformed_allowlist_fails_closed(transport):
    fake = _Fake([])
    with mock.patch.dict(os.environ, {"CONFLUENCE_SPACE_ALLOWLIST": "{not json"}):
        result = await _call(transport, _headers("create_page", ["ocp-paas-ops"]), "create_page",
                             {"space_key": "TECH", "title": "t", "body_html": "<p/>"}, fake)
    assert result.is_error and fake.requests == []


async def test_ctx_is_not_in_the_published_schemas(transport):
    http_client = httpx2.AsyncClient(transport=transport, base_url=BASE_URL, headers={"X-Zuno-Gateway-Token": TOKEN})
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
