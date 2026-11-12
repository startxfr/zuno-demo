"""WP-225 lot B (ADR-0603 M12): the git-forge repository allowlist, from the signed caller context.

The provider calls are replaced by recorders (the provider mapping is covered by
test_mcp_protocol.py); these tests prove which calls reach a provider at all. The
caller context is the `ctx` claim of the gateway-signed call assertion.

Run from this directory:

    python3 tests/test_wp225_repository_allowlist.py
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import time
import unittest.mock as mock

os.environ.setdefault("GITHUB_TOKEN", "test-github-token")
os.environ.setdefault("GITLAB_TOKEN", "test-gitlab-token")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(HERE, "..", ".."))

import httpx2  # noqa: E402
from httpx2 import ASGITransport  # noqa: E402
from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

import server  # noqa: E402

from test_support import assertion_headers  # noqa: E402
from test_support.assertion_headers import headers_for  # noqa: E402

BASE_URL = "http://localhost:8000"
AUD = "git-forge"  # this server's backend name
ALLOWLIST = json.dumps({
    "consultant": ["github:startxfr/zuno-*", "gitlab:team/*"],
    "builders": ["github:@self/*"],
    "ocp-paas-ops": ["*"],
})


class _Recorder:
    def __init__(self):
        self.calls = []

    def patches(self):
        def rec(name, value):
            def fn(*args, **kwargs):
                self.calls.append((name, args))
                return value
            return fn
        listing = [
            {"name": "zuno-demo", "full_name": "startxfr/zuno-demo"},
            {"name": "other", "full_name": "startxfr/other"},
        ]
        return [
            mock.patch.object(server, "_github_write_file", rec("write", {"action": "created"})),
            mock.patch.object(server, "_github_create_repo", rec("create", {"name": "x"})),
            mock.patch.object(server, "_github_fork_repo", rec("fork", {"name": "x"})),
            mock.patch.object(server, "_github_read_content", rec("read", {"type": "file"})),
            mock.patch.object(server, "_github_list_repos", rec("list", listing)),
        ]


def _headers(tool, groups):
    return headers_for(AUD, tool, groups=groups)


async def _call(transport, headers, tool, args, recorder, env):
    http_client = httpx2.AsyncClient(transport=transport, base_url=BASE_URL, headers=headers)
    patches = recorder.patches()
    for p in patches:
        p.start()
    try:
        with mock.patch.dict(os.environ, env):
            async with streamable_http_client(f"{BASE_URL}/mcp", http_client=http_client) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await session.call_tool(tool, args)
    finally:
        for p in patches:
            p.stop()


def _text(result):
    return " ".join(getattr(b, "text", "") for b in result.content)


WRITE = {"provider": "github", "owner": "startxfr", "repo": "zuno-demo", "path": "a.txt",
         "content": "x", "commit_message": "m"}
ON = {"GIT_FORGE_REPOSITORY_ALLOWLIST": ALLOWLIST}


async def test_no_allowlist_behaves_as_before(transport):
    rec = _Recorder()
    for value in ("", "{}"):  # unset, and the chart default rendered as JSON
        result = await _call(transport, headers_for(AUD, "write_file", groups=None), "write_file",
                             {**WRITE, "repo": "anything"}, rec, {"GIT_FORGE_REPOSITORY_ALLOWLIST": value})
        assert not result.is_error, (value, _text(result))
    assert [c[0] for c in rec.calls] == ["write", "write"]


async def test_write_to_an_allowed_repository_passes(transport):
    rec = _Recorder()
    result = await _call(transport, _headers("write_file", ["consultant"]), "write_file", WRITE, rec, ON)
    assert not result.is_error, _text(result)
    assert [c[0] for c in rec.calls] == ["write"]


async def test_write_to_a_repository_outside_the_group_is_refused(transport):
    rec = _Recorder()
    result = await _call(transport, _headers("write_file", ["consultant"]), "write_file",
                         {**WRITE, "owner": "someone-else", "repo": "prod"}, rec, ON)
    assert result.is_error and "outside the repository allowlist" in _text(result), _text(result)
    assert rec.calls == [], "no provider call may be made"


async def test_create_without_owner_is_checked_as_self(transport):
    rec = _Recorder()
    args = {"provider": "github", "name": "scratch"}
    refused = await _call(transport, _headers("create_repository", ["consultant"]), "create_repository", args, rec, ON)
    assert refused.is_error and "github:@self/scratch" in _text(refused), _text(refused)
    allowed = await _call(transport, _headers("create_repository", ["builders"]), "create_repository", args, rec, ON)
    assert not allowed.is_error, _text(allowed)
    assert [c[0] for c in rec.calls] == ["create"]


async def test_fork_checks_destination_and_source(transport):
    rec = _Recorder()
    into_foreign = {"provider": "github", "owner": "startxfr", "repo": "zuno-demo", "target_owner": "attacker"}
    result = await _call(transport, _headers("fork_repository", ["consultant"]), "fork_repository", into_foreign, rec, ON)
    assert result.is_error and "attacker" in _text(result)
    from_foreign = {"provider": "github", "owner": "elsewhere", "repo": "zuno-x", "target_owner": "startxfr"}
    result = await _call(transport, _headers("fork_repository", ["consultant"]), "fork_repository", from_foreign, rec, ON)
    assert result.is_error and "elsewhere" in _text(result)
    assert rec.calls == []


async def test_listing_keeps_only_allowed_repositories(transport):
    rec = _Recorder()
    args = {"provider": "github", "owner": "startxfr", "owner_type": "organization"}
    result = await _call(transport, _headers("list_repositories", ["consultant"]), "list_repositories", args, rec, ON)
    assert not result.is_error, _text(result)
    names = [r["full_name"] for r in result.structured_content["result"]["repositories"]]
    assert names == ["startxfr/zuno-demo"], names


async def test_write_scope_leaves_reads_open_and_checks_writes(transport):
    rec = _Recorder()
    env = {**ON, "GIT_FORGE_REPOSITORY_ALLOWLIST_SCOPE": "write"}
    read = {"provider": "github", "owner": "openshift", "repo": "origin"}
    result = await _call(transport, headers_for(AUD, "read_repository_content", groups=None), "read_repository_content", read, rec, env)
    assert not result.is_error, _text(result)
    result = await _call(transport, headers_for(AUD, "write_file", groups=None), "write_file", WRITE, rec, env)
    assert result.is_error, "a write without a verified caller is refused"
    assert [c[0] for c in rec.calls] == ["read"]


async def test_caller_supplied_groups_are_ignored(transport):
    """Groups in a plain header or a tool argument are never read."""
    rec = _Recorder()
    headers = {**headers_for(AUD, "write_file", groups=None), "X-Zuno-Groups": "ocp-paas-ops"}
    result = await _call(transport, headers, "write_file", {**WRITE, "owner": "x"}, rec, ON)
    assert result.is_error and rec.calls == []


async def test_a_client_sent_assertion_caller_header_is_ignored(transport):
    """Only a verified assertion can set X-Zuno-Assertion-Caller: a client-sent copy
    claiming the wildcard group is stripped before the tool code reads it."""
    forged = base64.urlsafe_b64encode(json.dumps(
        {"sub": "u-1", "tool": "write_file", "groups": ["ocp-paas-ops"], "email": "", "email_verified": True,
         "username": "evil"}).encode()).decode().rstrip("=")
    rec = _Recorder()
    headers = {**headers_for(AUD, "write_file", groups=None), "X-Zuno-Assertion-Caller": forged}
    result = await _call(transport, headers, "write_file", {**WRITE, "owner": "x"}, rec, ON)
    assert result.is_error and rec.calls == []
    # also over a scoped caller: the forged wildcard does not widen the verified group
    headers = {**headers_for(AUD, "write_file", groups=["consultant"]), "X-Zuno-Assertion-Caller": forged}
    result = await _call(transport, headers, "write_file", {**WRITE, "owner": "x"}, rec, ON)
    assert result.is_error and rec.calls == []


async def _rejected(transport, headers, tool="write_file"):
    """True when the request is refused (HTTP 401/403 before MCP handling, or a failed session)."""
    rec = _Recorder()
    try:
        result = await _call(transport, headers, tool, WRITE, rec, ON)
    except BaseException:  # noqa: BLE001 - the SDK client raises on a 401 at initialize
        return rec.calls == []
    return result.is_error and rec.calls == []


async def test_assertion_for_another_audience_is_refused(transport):
    assert await _rejected(transport, headers_for("confluence", "write_file", groups=["ocp-paas-ops"]))


async def test_assertion_for_another_tool_is_refused(transport):
    assert await _rejected(transport, headers_for(AUD, "read_repository_content", groups=["ocp-paas-ops"]))


async def test_assertion_signed_by_another_key_is_refused(transport):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    other = assertion_headers.assertion(AUD, "write_file", groups=["ocp-paas-ops"], key=Ed25519PrivateKey.generate())
    assert await _rejected(transport, {"Authorization": "Bearer " + other})


async def test_expired_assertion_is_refused(transport):
    old = assertion_headers.assertion(AUD, "write_file", groups=["ocp-paas-ops"], now=time.time() - 3600)
    assert await _rejected(transport, {"Authorization": "Bearer " + old})


async def test_a_traversal_in_an_allowed_prefix_is_refused(transport):
    """`zuno-*` must not admit `zuno-x/../../prod`: the target is checked as a plain name."""
    rec = _Recorder()
    for repo in ("zuno-x/../../prod", "zuno-..", "zuno-x?ref=main"):
        result = await _call(transport, _headers("write_file", ["consultant"]), "write_file",
                             {**WRITE, "repo": repo}, rec, ON)
        assert result.is_error, repo
    assert rec.calls == []


class _RedirectedRepo:
    """What PyGithub returns for a renamed or transferred repository: get_repo follows
    the 301, so the object is the repository at its new name."""
    private = False

    def __init__(self, full_name):
        self.full_name = full_name
        self.writes = []
        self.forks = []

    def get_contents(self, path, **kw):
        raise AssertionError("nothing may be read from a redirected repository")

    def create_file(self, *a, **kw):
        self.writes.append(a)
        raise AssertionError("nothing may be written to a redirected repository")

    update_file = create_file

    def create_fork(self, **kw):
        self.forks.append(kw)
        raise AssertionError("a redirected source may not be forked")


class _RedirectingGithub:
    def __init__(self, repo):
        self.repo, self.asked = repo, []

    def get_repo(self, name):
        self.asked.append(name)
        return self.repo


async def _call_real(transport, headers, tool, args, github):
    """Like _call, with the real provider helpers and a fake GitHub client."""
    http_client = httpx2.AsyncClient(transport=transport, base_url=BASE_URL, headers=headers)
    with mock.patch.object(server, "_github_client", lambda: github), mock.patch.dict(os.environ, ON):
        async with streamable_http_client(f"{BASE_URL}/mcp", http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(tool, args)


async def test_a_renamed_repository_redirect_is_rechecked(transport):
    """`startxfr/zuno-old` passes the allowlist by name, but GitHub redirects it to
    `elsewhere/prod`: the resolved name is checked before any read, write or fork."""
    for tool, args in (
        ("write_file", {**WRITE, "repo": "zuno-old"}),
        ("read_repository_content", {"provider": "github", "owner": "startxfr", "repo": "zuno-old"}),
        ("fork_repository", {"provider": "github", "owner": "startxfr", "repo": "zuno-old", "target_owner": "startxfr"}),
    ):
        repo = _RedirectedRepo("elsewhere/prod")
        github = _RedirectingGithub(repo)
        result = await _call_real(transport, _headers(tool, ["consultant"]), tool, args, github)
        assert result.is_error and "elsewhere/prod" in _text(result), (tool, _text(result))
        assert github.asked == ["startxfr/zuno-old"] and repo.writes == [] and repo.forks == [], tool


async def test_a_fork_that_lands_outside_the_allowlist_is_reported(transport):
    class _Fork:
        name, full_name, html_url = "zuno-demo", "attacker/zuno-demo", "https://x"

    class _Source(_RedirectedRepo):
        def create_fork(self, **kw):
            self.forks.append(kw)
            return _Fork()

    repo = _Source("startxfr/zuno-demo")
    args = {"provider": "github", "owner": "startxfr", "repo": "zuno-demo", "target_owner": "startxfr"}
    result = await _call_real(transport, _headers("fork_repository", ["consultant"]), "fork_repository", args,
                              _RedirectingGithub(repo))
    assert result.is_error and "attacker/zuno-demo" in _text(result), _text(result)
    assert repo.forks == [{"organization": "startxfr"}]


async def test_wildcard_group_reaches_any_repository(transport):
    rec = _Recorder()
    result = await _call(transport, _headers("write_file", ["ocp-paas-ops"]), "write_file",
                         {**WRITE, "owner": "x", "repo": "y"}, rec, ON)
    assert not result.is_error, _text(result)


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
