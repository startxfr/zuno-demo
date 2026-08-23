"""ADR-0043/ADR-0120 protocol tests for the git-forge MCP server: proves
this server's /mcp endpoint speaks real, standards-compliant MCP
streamable-HTTP (the official `mcp` SDK), exercised with the actual SDK
client against this server's real ASGI app in-process (no real socket) -
same style as every other server in components/mcp-servers/.

GitHub/GitLab themselves are mocked (`server._github_client`/
`server._gitlab_client` are patched to return fake, minimal client
objects) - these tests prove the MCP protocol surface and each tool's
request/response mapping, not a live GitHub/GitLab call.

The `delete_repository` tests are the most important ones here: they
prove the tool NEVER calls `_github_client`/`_gitlab_client` at all (not
just that it returns a "refused" payload) - the strongest guarantee
ADR-0120 makes.

Run from this directory:

    python3 tests/test_mcp_protocol.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest.mock as mock

os.environ.setdefault("MCP_GATEWAY_WORKLOAD_TOKEN", "test-workload-token")
os.environ.setdefault("GITHUB_TOKEN", "test-github-token")
os.environ.setdefault("GITLAB_TOKEN", "test-gitlab-token")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx2  # noqa: E402
from httpx2 import ASGITransport  # noqa: E402
from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

import server  # noqa: E402
from github.GithubException import UnknownObjectException  # noqa: E402
from gitlab.exceptions import GitlabGetError  # noqa: E402

BASE_URL = "http://localhost:8000"
GATEWAY_HEADERS = {"X-Zuno-Gateway-Token": "test-workload-token"}


async def _open_session(transport, headers):
    http_client = httpx2.AsyncClient(transport=transport, base_url=BASE_URL, headers=headers)
    return streamable_http_client(f"{BASE_URL}/mcp", http_client=http_client)


def _result(struct) -> dict:
    """See components/mcp-servers/confluence's own tests for why: a tool
    whose return type is a plain Dict[str, Any] gets wrapped as
    {"result": <value>} by the MCP SDK (object-typed top-level schema
    requirement)."""
    return struct["result"]


# --------------------------------------------------------------------------
# Fakes - minimal stand-ins for the PyGithub/python-gitlab objects
# server.py actually calls methods on.
# --------------------------------------------------------------------------


class _FakeGithubContentFile:
    def __init__(self, path: str, content: bytes, sha: str):
        self.path = path
        self.name = path.rsplit("/", 1)[-1]
        self.type = "file"
        self.sha = sha
        self.size = len(content)
        self.decoded_content = content


class _FakeGithubCommit:
    def __init__(self, sha: str, html_url: str):
        self.sha = sha
        self.html_url = html_url


class _FakeGithubRepo:
    def __init__(self, full_name: str, contents=None, fork_result=None, private: bool = False):
        self.full_name = full_name
        self.name = full_name.split("/")[-1]
        self._contents = contents or {}
        self._fork_result = fork_result
        self.private = private
        self.calls = []

    def get_contents(self, path, **kwargs):
        self.calls.append(("get_contents", path, kwargs.get("ref")))
        if path not in self._contents:
            raise UnknownObjectException(404, "Not Found", None)
        return self._contents[path]

    def create_file(self, path, message, content, **kwargs):
        self.calls.append(("create_file", path, message, content))
        return {"content": _FakeGithubContentFile(path, content.encode(), "new-sha"), "commit": _FakeGithubCommit("commit-sha-created", "https://github.com/o/r/commit/created")}

    def update_file(self, path, message, content, sha, **kwargs):
        self.calls.append(("update_file", path, message, content, sha))
        return {"content": _FakeGithubContentFile(path, content.encode(), "updated-sha"), "commit": _FakeGithubCommit("commit-sha-updated", "https://github.com/o/r/commit/updated")}

    def create_fork(self, **kwargs):
        self.calls.append(("create_fork", kwargs))
        return self._fork_result


class _FakeGithubRepoSummary:
    def __init__(self, name, full_name, private, description, html_url):
        self.name = name
        self.full_name = full_name
        self.private = private
        self.description = description
        self.html_url = html_url


class _FakeGithubAccount:
    def __init__(self, repos=None, created_repo=None):
        self._repos = repos or []
        self._created_repo = created_repo
        self.calls = []

    def get_repos(self):
        return self._repos

    def create_repo(self, name, **kwargs):
        self.calls.append(("create_repo", name, kwargs))
        return self._created_repo


class _FakeGithubClient:
    def __init__(self, repo=None, user=None, org=None):
        self._repo = repo
        self._user = user
        self._org = org

    def get_repo(self, full_name):
        assert self._repo is not None, f"unexpected get_repo({full_name!r})"
        return self._repo

    def get_user(self, login=None):
        assert self._user is not None, "unexpected get_user()"
        return self._user

    def get_organization(self, org):
        assert self._org is not None, f"unexpected get_organization({org!r})"
        return self._org


class _FakeGitlabProjectFile:
    def __init__(self, file_path, content_bytes, blob_id):
        self.file_path = file_path
        self.blob_id = blob_id
        self.size = len(content_bytes)
        self._content_bytes = content_bytes
        self.content = None
        self.saved_with = None

    def decode(self):
        return self._content_bytes

    def save(self, **kwargs):
        self.saved_with = kwargs
        self.last_commit_id = "gitlab-updated-commit"


class _FakeGitlabFilesManager:
    def __init__(self, files=None):
        self._files = files or {}
        self.created = []

    def get(self, file_path, ref):
        if file_path not in self._files:
            raise GitlabGetError(error_message="404 File Not Found", response_code=404)
        return self._files[file_path]

    def create(self, data):
        self.created.append(data)


class _FakeGitlabForksManager:
    def __init__(self, fork_result=None):
        self._fork_result = fork_result
        self.created_with = None

    def create(self, data):
        self.created_with = data
        return self._fork_result


class _FakeGitlabProject:
    def __init__(self, default_branch="main", files=None, tree=None, fork_result=None, visibility="public"):
        self.default_branch = default_branch
        self.files = _FakeGitlabFilesManager(files)
        self.forks = _FakeGitlabForksManager(fork_result)
        self.visibility = visibility
        self._tree = tree or []

    def repository_tree(self, path="", ref="", all=True, **kwargs):
        return self._tree


class _FakeGitlabProjectSummary:
    def __init__(self, name, full_name, url, private=True, description=None):
        self.name = name
        self.path_with_namespace = full_name
        self.web_url = url
        self.visibility = "private" if private else "public"
        self.description = description


class _FakeGitlabProjectsManager:
    def __init__(self, project=None, created=None):
        self._project = project
        self._created = created

    def get(self, path):
        assert self._project is not None, f"unexpected projects.get({path!r})"
        return self._project

    def create(self, data):
        return self._created


class _FakeGitlabClient:
    def __init__(self, project=None, created_project=None, http_list_by_path=None):
        self.projects = _FakeGitlabProjectsManager(project, created_project)
        self._http_list_by_path = http_list_by_path or {}

    def http_list(self, path, query_data=None, **kwargs):
        for prefix, result in self._http_list_by_path.items():
            if path.startswith(prefix):
                return result
        raise AssertionError(f"unexpected http_list({path!r}, {query_data!r})")


def _patch_github(fake_client):
    return mock.patch.object(server, "_github_client", lambda: fake_client)


def _patch_gitlab(fake_client):
    return mock.patch.object(server, "_gitlab_client", lambda: fake_client)


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


async def test_unauthenticated_call_rejected_before_any_protocol_handling(transport) -> None:
    async with httpx2.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0"},
            headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
        )
    assert resp.status_code == 401, f"expected 401 with no gateway token, got {resp.status_code}"


async def test_tools_list_reports_exactly_the_eight_declared_tools(transport) -> None:
    async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
    names = sorted(t.name for t in result.tools)
    assert names == [
        "create_repository",
        "delete_repository",
        "fork_repository",
        "list_private_repositories",
        "list_repositories",
        "read_private_repository_content",
        "read_repository_content",
        "write_file",
    ], names


async def test_read_repository_content_github_file(transport) -> None:
    repo = _FakeGithubRepo("acme/widgets", contents={"README.md": _FakeGithubContentFile("README.md", b"hello world", "abc123")})
    fake = _FakeGithubClient(repo=repo)
    with _patch_github(fake):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "read_repository_content",
                    {"provider": "github", "owner": "acme", "repo": "widgets", "path": "README.md"},
                )
    assert not result.is_error, result.content
    payload = _result(result.structured_content)
    assert payload["type"] == "file"
    assert payload["content"] == "hello world"
    assert payload["sha"] == "abc123"


async def test_read_repository_content_github_missing_path_is_a_tool_error(transport) -> None:
    repo = _FakeGithubRepo("acme/widgets", contents={})
    fake = _FakeGithubClient(repo=repo)
    with _patch_github(fake):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "read_repository_content",
                    {"provider": "github", "owner": "acme", "repo": "widgets", "path": "missing.txt"},
                )
    assert result.is_error


async def test_read_repository_content_gitlab_file(transport) -> None:
    project = _FakeGitlabProject(files={"README.md": _FakeGitlabProjectFile("README.md", b"bonjour", "blob-1")})
    fake = _FakeGitlabClient(project=project)
    with _patch_gitlab(fake):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "read_repository_content",
                    {"provider": "gitlab", "owner": "acme", "repo": "widgets", "path": "README.md"},
                )
    assert not result.is_error, result.content
    payload = _result(result.structured_content)
    assert payload["content"] == "bonjour"
    assert payload["sha"] == "blob-1"


async def test_read_repository_content_gitlab_directory(transport) -> None:
    tree = [{"name": "src", "path": "src", "type": "tree"}, {"name": "README.md", "path": "README.md", "type": "blob"}]
    project = _FakeGitlabProject(files={}, tree=tree)
    fake = _FakeGitlabClient(project=project)
    with _patch_gitlab(fake):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "read_repository_content",
                    {"provider": "gitlab", "owner": "acme", "repo": "widgets", "path": ""},
                )
    assert not result.is_error, result.content
    payload = _result(result.structured_content)
    assert payload["type"] == "directory"
    assert len(payload["entries"]) == 2


async def test_read_repository_content_refuses_private_github(transport) -> None:
    repo = _FakeGithubRepo("acme/secret", contents={"README.md": _FakeGithubContentFile("README.md", b"shh", "sha1")}, private=True)
    fake = _FakeGithubClient(repo=repo)
    with _patch_github(fake):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "read_repository_content",
                    {"provider": "github", "owner": "acme", "repo": "secret", "path": "README.md"},
                )
    assert result.is_error, "private GitHub content must never be readable via read_repository_content"
    assert not repo.calls, "must refuse before even calling get_contents"


async def test_read_repository_content_refuses_private_gitlab(transport) -> None:
    project = _FakeGitlabProject(files={"README.md": _FakeGitlabProjectFile("README.md", b"shh", "blob-1")}, visibility="private")
    fake = _FakeGitlabClient(project=project)
    with _patch_gitlab(fake):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "read_repository_content",
                    {"provider": "gitlab", "owner": "acme", "repo": "secret", "path": "README.md"},
                )
    assert result.is_error, "private GitLab content must never be readable via the public-only read_repository_content"


async def test_read_private_repository_content_allows_private_gitlab(transport) -> None:
    project = _FakeGitlabProject(files={"README.md": _FakeGitlabProjectFile("README.md", b"shh", "blob-1")}, visibility="private")
    fake = _FakeGitlabClient(project=project)
    with _patch_gitlab(fake):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "read_private_repository_content",
                    {"provider": "gitlab", "owner": "acme", "repo": "secret", "path": "README.md"},
                )
    assert not result.is_error, result.content
    payload = _result(result.structured_content)
    assert payload["content"] == "shh"


async def test_read_private_repository_content_refuses_github_provider(transport) -> None:
    def _boom():
        raise AssertionError("read_private_repository_content must never construct a GitHub client")

    with mock.patch.object(server, "_github_client", _boom):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "read_private_repository_content",
                    {"provider": "github", "owner": "acme", "repo": "secret"},
                )
    assert result.is_error, "read_private_repository_content must never accept provider='github'"


async def test_list_repositories_github_user(transport) -> None:
    repos = [_FakeGithubRepoSummary("widgets", "acme/widgets", False, "widgets repo", "https://github.com/acme/widgets")]
    fake = _FakeGithubClient(user=_FakeGithubAccount(repos=repos))
    with _patch_github(fake):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "list_repositories", {"provider": "github", "owner": "acme", "owner_type": "user"}
                )
    assert not result.is_error, result.content
    payload = _result(result.structured_content)
    assert payload["count"] == 1
    assert payload["repositories"][0]["full_name"] == "acme/widgets"


async def test_list_repositories_gitlab_organization(transport) -> None:
    projects = [
        {"name": "widgets", "path_with_namespace": "acme/widgets", "visibility": "public", "description": None, "web_url": "https://gitlab.com/acme/widgets"}
    ]
    fake = _FakeGitlabClient(http_list_by_path={"/groups/acme/projects": projects})
    with _patch_gitlab(fake):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "list_repositories", {"provider": "gitlab", "owner": "acme", "owner_type": "organization"}
                )
    assert not result.is_error, result.content
    payload = _result(result.structured_content)
    assert payload["count"] == 1
    assert payload["repositories"][0]["private"] is False


async def test_list_repositories_filters_out_private_github(transport) -> None:
    repos = [
        _FakeGithubRepoSummary("widgets", "acme/widgets", False, "public one", "https://github.com/acme/widgets"),
        _FakeGithubRepoSummary("secret", "acme/secret", True, "private one", "https://github.com/acme/secret"),
    ]
    fake = _FakeGithubClient(user=_FakeGithubAccount(repos=repos))
    with _patch_github(fake):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "list_repositories", {"provider": "github", "owner": "acme", "owner_type": "user"}
                )
    assert not result.is_error, result.content
    payload = _result(result.structured_content)
    assert payload["count"] == 1
    assert payload["repositories"][0]["full_name"] == "acme/widgets"


async def test_list_repositories_filters_out_private_gitlab(transport) -> None:
    projects = [
        {"name": "widgets", "path_with_namespace": "acme/widgets", "visibility": "public", "description": None, "web_url": "https://gitlab.com/acme/widgets"},
        {"name": "secret", "path_with_namespace": "acme/secret", "visibility": "private", "description": None, "web_url": "https://gitlab.com/acme/secret"},
    ]
    fake = _FakeGitlabClient(http_list_by_path={"/groups/acme/projects": projects})
    with _patch_gitlab(fake):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "list_repositories", {"provider": "gitlab", "owner": "acme", "owner_type": "organization"}
                )
    assert not result.is_error, result.content
    payload = _result(result.structured_content)
    assert payload["count"] == 1
    assert payload["repositories"][0]["full_name"] == "acme/widgets"


async def test_list_private_repositories_gitlab_includes_private(transport) -> None:
    projects = [
        {"name": "widgets", "path_with_namespace": "acme/widgets", "visibility": "public", "description": None, "web_url": "https://gitlab.com/acme/widgets"},
        {"name": "secret", "path_with_namespace": "acme/secret", "visibility": "private", "description": None, "web_url": "https://gitlab.com/acme/secret"},
    ]
    fake = _FakeGitlabClient(http_list_by_path={"/groups/acme/projects": projects})
    with _patch_gitlab(fake):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "list_private_repositories", {"provider": "gitlab", "owner": "acme", "owner_type": "organization"}
                )
    assert not result.is_error, result.content
    payload = _result(result.structured_content)
    assert payload["count"] == 2, "must include both the public and the private project"


async def test_list_private_repositories_refuses_github_provider(transport) -> None:
    def _boom():
        raise AssertionError("list_private_repositories must never construct a GitHub client")

    with mock.patch.object(server, "_github_client", _boom):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "list_private_repositories", {"provider": "github", "owner": "acme", "owner_type": "user"}
                )
    assert result.is_error, "list_private_repositories must never accept provider='github'"


async def test_write_file_github_creates_when_absent(transport) -> None:
    repo = _FakeGithubRepo("acme/widgets", contents={})
    fake = _FakeGithubClient(repo=repo)
    with _patch_github(fake):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "write_file",
                    {
                        "provider": "github",
                        "owner": "acme",
                        "repo": "widgets",
                        "path": "NEW.md",
                        "content": "new content",
                        "commit_message": "add NEW.md",
                    },
                )
    assert not result.is_error, result.content
    payload = _result(result.structured_content)
    assert payload["action"] == "created"
    assert repo.calls[-1][0] == "create_file"


async def test_write_file_github_updates_when_present(transport) -> None:
    repo = _FakeGithubRepo("acme/widgets", contents={"NEW.md": _FakeGithubContentFile("NEW.md", b"old", "old-sha")})
    fake = _FakeGithubClient(repo=repo)
    with _patch_github(fake):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "write_file",
                    {
                        "provider": "github",
                        "owner": "acme",
                        "repo": "widgets",
                        "path": "NEW.md",
                        "content": "new content",
                        "commit_message": "update NEW.md",
                    },
                )
    assert not result.is_error, result.content
    payload = _result(result.structured_content)
    assert payload["action"] == "updated"
    update_call = [c for c in repo.calls if c[0] == "update_file"][0]
    assert update_call[4] == "old-sha", "must pass the existing file's sha, not blindly overwrite"


async def test_write_file_gitlab_creates_when_absent(transport) -> None:
    project = _FakeGitlabProject(files={})
    fake = _FakeGitlabClient(project=project)
    with _patch_gitlab(fake):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "write_file",
                    {
                        "provider": "gitlab",
                        "owner": "acme",
                        "repo": "widgets",
                        "path": "NEW.md",
                        "content": "new content",
                        "commit_message": "add NEW.md",
                    },
                )
    assert not result.is_error, result.content
    payload = _result(result.structured_content)
    assert payload["action"] == "created"
    assert len(project.files.created) == 1


async def test_write_file_refuses_private_github(transport) -> None:
    repo = _FakeGithubRepo("acme/secret", contents={}, private=True)
    fake = _FakeGithubClient(repo=repo)
    with _patch_github(fake):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "write_file",
                    {
                        "provider": "github",
                        "owner": "acme",
                        "repo": "secret",
                        "path": "NEW.md",
                        "content": "x",
                        "commit_message": "add NEW.md",
                    },
                )
    assert result.is_error, "must never write to a private GitHub repository"
    assert not repo.calls, "must refuse before calling create_file/update_file"


async def test_write_file_refuses_private_gitlab(transport) -> None:
    project = _FakeGitlabProject(files={}, visibility="private")
    fake = _FakeGitlabClient(project=project)
    with _patch_gitlab(fake):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "write_file",
                    {
                        "provider": "gitlab",
                        "owner": "acme",
                        "repo": "secret",
                        "path": "NEW.md",
                        "content": "x",
                        "commit_message": "add NEW.md",
                    },
                )
    assert result.is_error, "must never write to a private GitLab project"
    assert not project.files.created, "must refuse before calling files.create"


async def test_create_repository_github(transport) -> None:
    created = _FakeGithubRepoSummary("widgets", "acme/widgets", True, "", "https://github.com/acme/widgets")
    fake = _FakeGithubClient(org=_FakeGithubAccount(created_repo=created))
    with _patch_github(fake):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "create_repository",
                    {"provider": "github", "name": "widgets", "owner": "acme", "private": True},
                )
    assert not result.is_error, result.content
    payload = _result(result.structured_content)
    assert payload["full_name"] == "acme/widgets"


async def test_fork_repository_github(transport) -> None:
    fork = _FakeGithubRepoSummary("widgets", "someone-else/widgets", True, "", "https://github.com/someone-else/widgets")
    repo = _FakeGithubRepo("acme/widgets", fork_result=fork)
    fake = _FakeGithubClient(repo=repo)
    with _patch_github(fake):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "fork_repository", {"provider": "github", "owner": "acme", "repo": "widgets"}
                )
    assert not result.is_error, result.content
    payload = _result(result.structured_content)
    assert payload["full_name"] == "someone-else/widgets"


async def test_delete_repository_github_always_refuses_and_never_touches_a_client(transport) -> None:
    def _boom():
        raise AssertionError("delete_repository must never construct a GitHub client")

    with mock.patch.object(server, "_github_client", _boom), mock.patch.object(server, "_gitlab_client", _boom):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "delete_repository", {"provider": "github", "owner": "acme", "repo": "widgets"}
                )
    assert not result.is_error, result.content
    payload = _result(result.structured_content)
    assert payload["refused"] is True
    assert "delete_repo" in " ".join(payload["manual_instructions"])


async def test_delete_repository_gitlab_always_refuses_and_never_touches_a_client(transport) -> None:
    def _boom():
        raise AssertionError("delete_repository must never construct a GitLab client")

    with mock.patch.object(server, "_github_client", _boom), mock.patch.object(server, "_gitlab_client", _boom):
        async with await _open_session(transport, GATEWAY_HEADERS) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "delete_repository", {"provider": "gitlab", "owner": "acme", "repo": "widgets"}
                )
    assert not result.is_error, result.content
    payload = _result(result.structured_content)
    assert payload["refused"] is True
    assert "Owner" in " ".join(payload["manual_instructions"])


async def test_github_client_constructs_without_mocking(transport) -> None:
    """Unlike every other test here, this deliberately does NOT mock
    server._github_client - it calls the real factory (real Github(...)
    constructor, no network call triggered by construction alone) to catch
    argument-type bugs the mocked tests can never see. Caught a real bug
    live: PyGithub 2.9.1's Github.__init__ asserts isinstance(timeout, int),
    but HTTP_TIMEOUT_SECONDS is a float - every GitHub call failed at
    construction time until this was cast with int()."""
    client = server._github_client()
    assert client is not None


TESTS = [
    test_unauthenticated_call_rejected_before_any_protocol_handling,
    test_github_client_constructs_without_mocking,
    test_tools_list_reports_exactly_the_eight_declared_tools,
    test_read_repository_content_github_file,
    test_read_repository_content_github_missing_path_is_a_tool_error,
    test_read_repository_content_gitlab_file,
    test_read_repository_content_gitlab_directory,
    test_read_repository_content_refuses_private_github,
    test_read_repository_content_refuses_private_gitlab,
    test_read_private_repository_content_allows_private_gitlab,
    test_read_private_repository_content_refuses_github_provider,
    test_list_repositories_github_user,
    test_list_repositories_gitlab_organization,
    test_list_repositories_filters_out_private_github,
    test_list_repositories_filters_out_private_gitlab,
    test_list_private_repositories_gitlab_includes_private,
    test_list_private_repositories_refuses_github_provider,
    test_write_file_github_creates_when_absent,
    test_write_file_github_updates_when_present,
    test_write_file_gitlab_creates_when_absent,
    test_write_file_refuses_private_github,
    test_write_file_refuses_private_gitlab,
    test_create_repository_github,
    test_fork_repository_github,
    test_delete_repository_github_always_refuses_and_never_touches_a_client,
    test_delete_repository_gitlab_always_refuses_and_never_touches_a_client,
]


async def _run_all() -> int:
    transport = ASGITransport(app=server.app)
    lifespan_cm = server.app.router.lifespan_context(server.app)
    await lifespan_cm.__aenter__()

    failures = 0
    try:
        for test in TESTS:
            try:
                await test(transport)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {test.__name__}: {exc}")
            else:
                print(f"PASS {test.__name__}")
    finally:
        await lifespan_cm.__aexit__(None, None, None)
    return failures


def main() -> int:
    failures = asyncio.run(_run_all())
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
