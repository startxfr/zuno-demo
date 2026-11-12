"""WP-225 lot B (ADR-0603 M15): the per-caller limit on cluster_audit launches.

The AAP launch itself is replaced by a recorder (test_mcp_protocol.py covers it);
these tests prove which calls reach it. The caller is the `sub` of the caller
context signed by the gateway's own module.

Run from this directory:

    python3 tests/test_wp225_launch_rate_limit.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest.mock as mock

os.environ.setdefault("AAP_API_TOKEN", "test-token")
os.environ.setdefault("AAP_BASE_URL", "http://aap.zuno-aap.svc")

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
AUD = "aap"  # this server's backend name
LIMIT = {"AAP_CLUSTER_AUDIT_RATE_LIMIT": "2", "AAP_CLUSTER_AUDIT_RATE_WINDOW_SECONDS": "900"}


class _Launcher:
    def __init__(self, fail=False):
        self.count, self.fail = 0, fail

    async def __call__(self, progress=None):
        self.count += 1
        if self.fail:
            raise ValueError("AAP Controller is unreachable")
        return {"launched": True, "job": {"id": self.count}}


def _headers(sub):
    return headers_for(AUD, "cluster_audit", groups=["ocp-ai-ops"], sub=sub)


async def _launch(transport, headers, launcher, env):
    http_client = httpx2.AsyncClient(transport=transport, base_url=BASE_URL, headers=headers)
    with mock.patch.object(server, "_launch_cluster_audit", launcher), mock.patch.dict(os.environ, env):
        async with streamable_http_client(f"{BASE_URL}/mcp", http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool("cluster_audit", {})


def _text(result):
    return " ".join(getattr(b, "text", "") for b in result.content)


def _reset():
    server._launches.clear()


async def test_a_caller_past_the_limit_is_refused_without_a_launch(transport):
    _reset()
    launcher = _Launcher()
    for _ in range(2):
        result = await _launch(transport, _headers("alice"), launcher, LIMIT)
        assert not result.is_error, _text(result)
    refused = await _launch(transport, _headers("alice"), launcher, LIMIT)
    assert refused.is_error and "rate limited" in _text(refused), _text(refused)
    assert launcher.count == 2, "the third launch must never reach AAP"


async def test_the_limit_is_per_caller(transport):
    _reset()
    launcher = _Launcher()
    for _ in range(2):
        await _launch(transport, _headers("alice"), launcher, LIMIT)
    result = await _launch(transport, _headers("bob"), launcher, LIMIT)
    assert not result.is_error, _text(result)
    assert launcher.count == 3


async def test_unverified_calls_share_one_bucket(transport):
    """Without a `ctx` claim in the assertion, a caller cannot get a fresh bucket by changing
    its sub: every such call counts against the same one."""
    _reset()
    launcher = _Launcher()
    for sub in ("x", "y"):
        await _launch(transport, headers_for(AUD, "cluster_audit", groups=None, sub=sub), launcher, LIMIT)
    refused = await _launch(transport, headers_for(AUD, "cluster_audit", groups=None, sub="z"), launcher, LIMIT)
    assert refused.is_error and launcher.count == 2


async def test_a_refused_launch_does_not_count(transport):
    _reset()
    failing = _Launcher(fail=True)
    for _ in range(3):
        result = await _launch(transport, _headers("carol"), failing, LIMIT)
        assert result.is_error and "unreachable" in _text(result), _text(result)
    ok = await _launch(transport, _headers("carol"), _Launcher(), LIMIT)
    assert not ok.is_error, _text(ok)


class _NoClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


async def test_a_failure_after_a_successful_post_still_counts(transport):
    """The real launch path: the POST succeeds (the job exists), then the status read
    fails. The slot is kept, so retrying cannot launch past the limit."""
    _reset()
    posts = []

    async def fake_request(client, method, path, **kwargs):
        if method == "GET" and path.endswith("/job_templates/"):
            return {"results": [{"id": 3, "name": server.JOB_TEMPLATE_NAME}]}
        if method == "POST":
            posts.append(path)
            return {"id": 40 + len(posts)}
        raise ValueError("AAP Controller did not answer within 20s (GET job status)")

    async def launch(headers):
        http_client = httpx2.AsyncClient(transport=transport, base_url=BASE_URL, headers=headers)
        with mock.patch.object(server, "_client", lambda: _NoClient()), \
                mock.patch.object(server, "_request", fake_request), mock.patch.dict(os.environ, LIMIT):
            async with streamable_http_client(f"{BASE_URL}/mcp", http_client=http_client) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await session.call_tool("cluster_audit", {})

    for _ in range(2):
        result = await launch(_headers("frank"))
        assert result.is_error and "did not answer" in _text(result), _text(result)
    refused = await launch(_headers("frank"))
    assert refused.is_error and "rate limited" in _text(refused), _text(refused)
    assert len(posts) == 2, posts


async def test_a_failure_before_the_post_does_not_count_and_buckets_are_pruned(transport):
    _reset()

    async def fake_request(client, method, path, **kwargs):
        raise ValueError("AAP Controller is unreachable")

    with mock.patch.object(server, "_client", lambda: _NoClient()), \
            mock.patch.object(server, "_request", fake_request), mock.patch.dict(os.environ, LIMIT):
        for _ in range(3):
            try:
                await server.cluster_audit()
            except ValueError:
                pass
    assert server._launches == {}, server._launches
    with mock.patch.dict(os.environ, LIMIT):
        server._reserve_launch("old", now=0.0)
        server._reserve_launch("new", now=1000.0)
    assert list(server._launches) == ["new"], server._launches


async def test_window_expiry_frees_the_caller(transport):
    _reset()
    server._reserve_launch("dave", now=0.0)
    server._reserve_launch("dave", now=1.0)
    with mock.patch.dict(os.environ, LIMIT):
        try:
            server._reserve_launch("dave", now=2.0)
        except server.RateLimited:
            pass
        else:
            raise AssertionError("the third launch inside the window was accepted")
        assert server._reserve_launch("dave", now=901.0) == 901.0


async def test_zero_disables_the_limit(transport):
    _reset()
    launcher = _Launcher()
    for _ in range(5):
        result = await _launch(transport, _headers("erin"), launcher, {"AAP_CLUSTER_AUDIT_RATE_LIMIT": "0"})
        assert not result.is_error
    assert launcher.count == 5


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
