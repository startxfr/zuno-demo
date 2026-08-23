"""git-forge MCP server (ADR-0120, protocol per ADR-0043).

Zuno's first multi-provider external MCP integration: a single real,
standards-compliant MCP server (the `mcp` SDK's `MCPServer`,
streamable-HTTP transport, mounted at /mcp - same shape as every other
server in components/mcp-servers/) fronting BOTH the GitHub REST API (via
`PyGithub`) and the GitLab REST API (via `python-gitlab`), selected per
call by an explicit `provider: "github" | "gitlab"` tool argument rather
than deploying one server per platform (per ADR-0120's decision).

Exposes eight capabilities (`git.*`, ADR-0116 naming):
`git.repository.read`, `git.repository.list`, `git.repository.private.read`,
`git.repository.private.list`, `git.file.write`, `git.repository.create`,
`git.repository.fork`, `git.repository.delete` (tool functions below:
`read_repository_content`, `list_repositories`,
`read_private_repository_content`, `list_private_repositories`,
`write_file`, `create_repository`, `fork_repository`,
`delete_repository` - the MCP Gateway's binding registry maps the
logical capability ID to whichever `provider_tool` name this server
actually exposes, per ADR-0116).

`delete_repository` ALWAYS refuses and explains the manual steps instead
- see its own docstring. This is a deliberate product decision (ADR-0120),
not a missing feature: the function body never instantiates a GitHub/
GitLab client or makes any network call, so no credential scope or
authorization bug anywhere else in this file can accidentally cause a
real deletion.

ADR-0121 extends the same "refuse by construction" philosophy to
visibility: `read_repository_content`/`list_repositories`/`write_file`
ALWAYS refuse or filter out private content, on EITHER provider - a
hard, caller-independent server rule, not something policy alone is
trusted to enforce (this server has no per-caller identity to check,
service-identity auth, by design - see ADR-0208). Private access exists
only through `read_private_repository_content`/`list_private_repositories`,
which additionally refuse any provider other than `"gitlab"` - this
server never grants private GitHub access to anyone, full stop. Which
AGENT can reach the private-capable tools at all is still governed the
normal way, by OKF `allowed_tools` + `policies/tools/tool-policy.yaml`
(ADR-0011) - e.g. Arkos declares them, Tekos doesn't.

Authentication mode is `service-identity` (ADR-0208): one shared
technical identity per provider (`GITHUB_TOKEN`, `GITLAB_TOKEN`), sourced
from ExternalSecrets resolving `zuno/github/technical` and
`zuno/gitlab/technical` (never hardcoded, ADR-0024). Per ADR-0120's
Security considerations, the operator-provisioned GitHub token must NOT
carry the `delete_repo` scope and the GitLab token's account must NOT
have the Owner role on any project this server can reach - defense in
depth alongside the application-level refusal above, documented in this
component's README, not enforced in code (this server has no way to
introspect its own token's granted scopes before the provider rejects a
call that needs them).

    POST /mcp    - real MCP streamable-HTTP transport (initialize,
                   tools/list, tools/call)
    GET /healthz -> 200 once at least one of GITHUB_TOKEN/GITLAB_TOKEN is
                   configured (per-provider degradation: a call for the
                   unconfigured provider fails with a clear config error
                   at call time, rather than taking the whole server down
                   over one provider being unset). Deliberately does NOT
                   make a live GitHub/GitLab call on every probe - a
                   Kubernetes liveness/readiness probe firing every
                   ~10-15s against a real external SaaS API would be a
                   needless, avoidable load/quota cost.
"""
from __future__ import annotations

import asyncio
import hmac
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import quote

import gitlab
import gitlab.exceptions
from fastapi import FastAPI
from github import Auth, Github
from github.GithubException import UnknownObjectException
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN", "")
GITLAB_BASE_URL = os.getenv("GITLAB_BASE_URL", "https://gitlab.com")
HTTP_TIMEOUT_SECONDS = float(os.getenv("GIT_FORGE_HTTP_TIMEOUT_SECONDS", "20"))

# ADR-0037: required, not optional - this server has no purpose other than
# serving the gateway (same reasoning as every other server in
# components/mcp-servers/).
GATEWAY_WORKLOAD_TOKEN = os.getenv("MCP_GATEWAY_WORKLOAD_TOKEN", "")

Provider = Literal["github", "gitlab"]


class GitForgeConfigError(RuntimeError):
    pass


def _require_provider(provider: str) -> None:
    if provider not in ("github", "gitlab"):
        raise ValueError(f"unknown provider {provider!r} - expected 'github' or 'gitlab'")


def _github_client() -> Github:
    if not GITHUB_TOKEN:
        raise GitForgeConfigError(
            "GITHUB_TOKEN is required for provider='github' (sourced from an "
            "ExternalSecret against secret/zuno/github/technical - never "
            "hardcoded, ADR-0024)"
        )
    # PyGithub 2.9.1's Github.__init__ asserts isinstance(timeout, int) - a
    # bare float (e.g. the 20.0 HTTP_TIMEOUT_SECONDS defaults to) trips that
    # assertion and every GitHub call fails before ever reaching the network.
    return Github(auth=Auth.Token(GITHUB_TOKEN), timeout=int(HTTP_TIMEOUT_SECONDS))


def _gitlab_client() -> gitlab.Gitlab:
    if not GITLAB_TOKEN:
        raise GitForgeConfigError(
            "GITLAB_TOKEN is required for provider='gitlab' (sourced from an "
            "ExternalSecret against secret/zuno/gitlab/technical - never "
            "hardcoded, ADR-0024)"
        )
    return gitlab.Gitlab(GITLAB_BASE_URL, private_token=GITLAB_TOKEN, timeout=HTTP_TIMEOUT_SECONDS)


# --------------------------------------------------------------------------
# git.repository.read - read_repository_content / read_private_repository_content
# --------------------------------------------------------------------------

def _github_read_content(owner: str, repo: str, path: str, ref: Optional[str]) -> Dict[str, Any]:
    gh_repo = _github_client().get_repo(f"{owner}/{repo}")
    # ADR-0121: unconditional, caller-independent - this server never reads
    # private GitHub content through any tool, including the private-scoped
    # one (which refuses provider="github" entirely - see its own docstring).
    if gh_repo.private:
        raise ValueError(
            f"{owner}/{repo} is a private GitHub repository - this server "
            "never reads private GitHub content (private access is "
            "GitLab-only via read_private_repository_content, ADR-0121)"
        )
    kwargs = {"ref": ref} if ref else {}
    try:
        contents = gh_repo.get_contents(path or "", **kwargs)
    except UnknownObjectException:
        raise ValueError(f"no such GitHub content: {owner}/{repo}:{path or '/'}")

    if isinstance(contents, list):
        return {
            "type": "directory",
            "path": path or "",
            "entries": [
                {"name": c.name, "path": c.path, "type": c.type, "size": c.size} for c in contents
            ],
        }
    return {
        "type": "file",
        "path": contents.path,
        "size": contents.size,
        "sha": contents.sha,
        "content": contents.decoded_content.decode("utf-8", errors="replace"),
    }


def _gitlab_read_content(
    owner: str, repo: str, path: str, ref: Optional[str], *, allow_private: bool
) -> Dict[str, Any]:
    project = _gitlab_client().projects.get(f"{owner}/{repo}")
    if project.visibility != "public" and not allow_private:
        raise ValueError(
            f"{owner}/{repo} is not a public GitLab project (visibility="
            f"{project.visibility!r}) - use read_private_repository_content "
            "for private/internal access (ADR-0121)"
        )
    resolved_ref = ref or project.default_branch

    if path:
        try:
            file_ = project.files.get(file_path=path, ref=resolved_ref)
            return {
                "type": "file",
                "path": file_.file_path,
                "size": getattr(file_, "size", None),
                "sha": file_.blob_id,
                "content": file_.decode().decode("utf-8", errors="replace"),
            }
        except gitlab.exceptions.GitlabGetError as exc:
            if exc.response_code != 404:
                raise
            # Not a file at this path - fall through and try it as a directory.

    tree = project.repository_tree(path=path or "", ref=resolved_ref, all=True)
    if path and not tree:
        raise ValueError(f"no such GitLab content: {owner}/{repo}:{path}")
    return {
        "type": "directory",
        "path": path or "",
        "entries": [{"name": e["name"], "path": e["path"], "type": e["type"]} for e in tree],
    }


# --------------------------------------------------------------------------
# git.repository.list - list_repositories / list_private_repositories
# --------------------------------------------------------------------------

def _github_list_repos(owner: str, owner_type: str) -> List[Dict[str, Any]]:
    gh = _github_client()
    account = gh.get_organization(owner) if owner_type == "organization" else gh.get_user(owner)
    # ADR-0121: unconditional - GitHub listings from this server are always
    # public-only, on every tool (there is no private-scoped GitHub listing).
    return [
        {
            "name": r.name,
            "full_name": r.full_name,
            "private": r.private,
            "description": r.description,
            "url": r.html_url,
        }
        for r in account.get_repos()
        if not r.private
    ]


def _gitlab_list_repos(owner: str, owner_type: str, *, allow_private: bool) -> List[Dict[str, Any]]:
    gl = _gitlab_client()
    # python-gitlab has no dedicated "list a user's/group's projects"
    # object manager for this shape - `http_list` is the documented
    # low-level escape hatch wrapping the same REST endpoints the object
    # managers use internally.
    if owner_type == "organization":
        projects = gl.http_list(f"/groups/{quote(owner, safe='')}/projects", all=True)
    else:
        users = gl.http_list("/users", query_data={"username": owner})
        if not users:
            raise ValueError(f"no such GitLab user: {owner}")
        projects = gl.http_list(f"/users/{users[0]['id']}/projects", all=True)

    results = [
        {
            "name": p["name"],
            "full_name": p["path_with_namespace"],
            "private": p.get("visibility", "private") != "public",
            "description": p.get("description"),
            "url": p["web_url"],
        }
        for p in projects
    ]
    if not allow_private:
        results = [r for r in results if not r["private"]]
    return results


# --------------------------------------------------------------------------
# git.file.write - write_file (create-or-update, one commit)
# --------------------------------------------------------------------------

def _github_write_file(
    owner: str, repo: str, path: str, content: str, commit_message: str, branch: Optional[str]
) -> Dict[str, Any]:
    gh_repo = _github_client().get_repo(f"{owner}/{repo}")
    # ADR-0121: unconditional, caller-independent - this server only ever
    # writes to public repositories, on either provider.
    if gh_repo.private:
        raise ValueError(
            f"{owner}/{repo} is a private GitHub repository - this server "
            "only writes to public repositories (ADR-0121)"
        )
    kwargs = {"branch": branch} if branch else {}
    try:
        existing = gh_repo.get_contents(path, **kwargs)
        result = gh_repo.update_file(path, commit_message, content, existing.sha, **kwargs)
        action = "updated"
    except UnknownObjectException:
        result = gh_repo.create_file(path, commit_message, content, **kwargs)
        action = "created"
    commit = result["commit"]
    return {"action": action, "path": path, "commit_sha": commit.sha, "commit_url": commit.html_url}


def _gitlab_write_file(
    owner: str, repo: str, path: str, content: str, commit_message: str, branch: Optional[str]
) -> Dict[str, Any]:
    project = _gitlab_client().projects.get(f"{owner}/{repo}")
    # ADR-0121: unconditional, caller-independent - this server only ever
    # writes to public repositories, on either provider.
    if project.visibility != "public":
        raise ValueError(
            f"{owner}/{repo} is not a public GitLab project (visibility="
            f"{project.visibility!r}) - this server only writes to public "
            "repositories (ADR-0121)"
        )
    resolved_branch = branch or project.default_branch
    try:
        file_ = project.files.get(file_path=path, ref=resolved_branch)
        file_.content = content
        file_.save(branch=resolved_branch, commit_message=commit_message)
        action = "updated"
        commit_sha = getattr(file_, "last_commit_id", None)
    except gitlab.exceptions.GitlabGetError as exc:
        if exc.response_code != 404:
            raise
        project.files.create(
            {
                "file_path": path,
                "branch": resolved_branch,
                "content": content,
                "commit_message": commit_message,
            }
        )
        action = "created"
        commit_sha = None
    return {"action": action, "path": path, "commit_sha": commit_sha}


# --------------------------------------------------------------------------
# git.repository.create - create_repository
# --------------------------------------------------------------------------

def _github_create_repo(name: str, owner: Optional[str], private: bool, description: str) -> Dict[str, Any]:
    gh = _github_client()
    account = gh.get_organization(owner) if owner else gh.get_user()
    repo = account.create_repo(name, private=private, description=description)
    return {"name": repo.name, "full_name": repo.full_name, "url": repo.html_url, "private": repo.private}


def _gitlab_create_repo(name: str, owner: Optional[str], private: bool, description: str) -> Dict[str, Any]:
    gl = _gitlab_client()
    payload: Dict[str, Any] = {
        "name": name,
        "visibility": "private" if private else "public",
        "description": description,
    }
    if owner:
        namespaces = gl.http_list("/namespaces", query_data={"search": owner})
        if not namespaces:
            raise ValueError(f"no such GitLab namespace: {owner}")
        payload["namespace_id"] = namespaces[0]["id"]
    project = gl.projects.create(payload)
    return {
        "name": project.name,
        "full_name": project.path_with_namespace,
        "url": project.web_url,
        "private": project.visibility != "public",
    }


# --------------------------------------------------------------------------
# git.repository.fork - fork_repository
# --------------------------------------------------------------------------

def _github_fork_repo(owner: str, repo: str, target_owner: Optional[str]) -> Dict[str, Any]:
    gh_repo = _github_client().get_repo(f"{owner}/{repo}")
    kwargs = {"organization": target_owner} if target_owner else {}
    fork = gh_repo.create_fork(**kwargs)
    return {"name": fork.name, "full_name": fork.full_name, "url": fork.html_url}


def _gitlab_fork_repo(owner: str, repo: str, target_owner: Optional[str]) -> Dict[str, Any]:
    project = _gitlab_client().projects.get(f"{owner}/{repo}")
    payload = {"namespace": target_owner} if target_owner else {}
    fork = project.forks.create(payload)
    return {
        "name": fork.name,
        "full_name": getattr(fork, "path_with_namespace", fork.name),
        "url": getattr(fork, "web_url", None),
    }


# --------------------------------------------------------------------------
# git.repository.delete - ALWAYS refused, per ADR-0120. No client is ever
# instantiated and no network call is ever attempted in this function -
# see the module docstring for why that matters.
# --------------------------------------------------------------------------

_DELETE_INSTRUCTIONS: Dict[str, List[str]] = {
    "github": [
        "Sign in as an account with Admin/Owner rights on the repository "
        "(this server's own credential deliberately lacks the delete_repo scope).",
        "Go to https://github.com/<owner>/<repo>/settings, scroll to the "
        "'Danger Zone', click 'Delete this repository'.",
        "Type the repository's full name (<owner>/<repo>) to confirm.",
        "Alternative: DELETE /repos/<owner>/<repo> via the GitHub REST API, "
        "with a token that has the delete_repo scope.",
    ],
    "gitlab": [
        "Sign in as an account with the Owner role on the project "
        "(this server's own credential deliberately is not granted Owner).",
        "Go to the project's Settings > General > Advanced, click 'Delete project'.",
        "Depending on the namespace's tier/settings, deletion may be immediate "
        "or scheduled after a delay window.",
        "Alternative: DELETE /api/v4/projects/<id> via the GitLab REST API, "
        "with an Owner-scoped token.",
    ],
}


# --------------------------------------------------------------------------
# MCP server wiring
# --------------------------------------------------------------------------

mcp_server = MCPServer(
    name="git-forge",
    version="0.1.0",
    instructions=(
        "Read and write access to GitHub and GitLab repositories - every "
        "tool takes an explicit provider: \"github\" or \"gitlab\" argument. "
        "Repository deletion is never performed: delete_repository always "
        "explains the manual steps for the given provider instead of "
        "deleting anything."
    ),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Same requirement as every other server in components/mcp-servers/:
    # the mounted MCP sub-app's session manager needs the parent app's
    # lifespan to run its task group.
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(title="git-forge MCP server", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    if not (GITHUB_TOKEN or GITLAB_TOKEN):
        raise GitForgeConfigError("at least one of GITHUB_TOKEN/GITLAB_TOKEN must be configured")
    return {"status": "ok"}


@mcp_server.tool()
async def read_repository_content(
    provider: Provider, owner: str, repo: str, path: str = "", ref: Optional[str] = None
) -> Dict[str, Any]:
    """Read a file's content, or list a directory, in a PUBLIC GitHub or
    GitLab repository. Refuses if the repository is private, on either
    provider. Empty path reads the repository root. For GitLab private/
    internal access, use read_private_repository_content instead (GitLab
    only - this server never grants private GitHub access)."""
    _require_provider(provider)
    if provider == "github":
        return _github_read_content(owner, repo, path, ref)
    return _gitlab_read_content(owner, repo, path, ref, allow_private=False)


@mcp_server.tool()
async def read_private_repository_content(
    provider: Provider, owner: str, repo: str, path: str = "", ref: Optional[str] = None
) -> Dict[str, Any]:
    """Read a file's content, or list a directory, in a GitLab repository
    regardless of visibility (public, internal, or private). GitLab only -
    refuses provider="github"; this server never grants private GitHub
    access. For public repos on either provider, use
    read_repository_content instead."""
    _require_provider(provider)
    if provider != "gitlab":
        raise ValueError(
            "read_private_repository_content only supports provider='gitlab' "
            "- this server never grants private GitHub access (ADR-0121)"
        )
    return _gitlab_read_content(owner, repo, path, ref, allow_private=True)


@mcp_server.tool()
async def list_repositories(provider: Provider, owner: str, owner_type: Literal["user", "organization"]) -> Dict[str, Any]:
    """List the PUBLIC repositories owned by a GitHub user/organization or a
    GitLab user/group. Private/internal repositories are always filtered
    out, on either provider. For GitLab private/internal listings, use
    list_private_repositories instead (GitLab only)."""
    _require_provider(provider)
    # asyncio.to_thread: _github_list_repos/_gitlab_list_repos are
    # synchronous, blocking calls (PyGithub/python-gitlab both wrap
    # `requests`) that page through the account's full repo list -
    # potentially dozens of sequential HTTP round-trips for a large real
    # org. Running that directly in this async def would block the whole
    # single-worker event loop for the entire pagination, starving every
    # other in-flight session (including health checks) - live-cluster-
    # confirmed 2026-08-23: a large-org listing left the server returning
    # 503 to a concurrent request for the rest of that window.
    repos = await (
        asyncio.to_thread(_github_list_repos, owner, owner_type)
        if provider == "github"
        else asyncio.to_thread(_gitlab_list_repos, owner, owner_type, allow_private=False)
    )
    return {"owner": owner, "owner_type": owner_type, "repositories": repos, "count": len(repos)}


@mcp_server.tool()
async def list_private_repositories(provider: Provider, owner: str, owner_type: Literal["user", "organization"]) -> Dict[str, Any]:
    """List EVERY repository (public, internal, AND private) owned by a
    GitLab user/group - not a private-only filter. GitLab only - refuses
    provider="github"; this server never grants private GitHub access."""
    _require_provider(provider)
    if provider != "gitlab":
        raise ValueError(
            "list_private_repositories only supports provider='gitlab' "
            "- this server never grants private GitHub access (ADR-0121)"
        )
    # See list_repositories's own comment for why this is offloaded to a
    # thread rather than called directly.
    repos = await asyncio.to_thread(_gitlab_list_repos, owner, owner_type, allow_private=True)
    return {"owner": owner, "owner_type": owner_type, "repositories": repos, "count": len(repos)}


@mcp_server.tool()
async def write_file(
    provider: Provider,
    owner: str,
    repo: str,
    path: str,
    content: str,
    commit_message: str,
    branch: Optional[str] = None,
) -> Dict[str, Any]:
    """Create or update a file in a GitHub or GitLab repository as a single commit."""
    _require_provider(provider)
    if provider == "github":
        return _github_write_file(owner, repo, path, content, commit_message, branch)
    return _gitlab_write_file(owner, repo, path, content, commit_message, branch)


@mcp_server.tool()
async def create_repository(
    provider: Provider,
    name: str,
    owner: Optional[str] = None,
    private: bool = True,
    description: str = "",
) -> Dict[str, Any]:
    """Create a new repository. `owner` is a GitHub organization or a GitLab
    namespace (user/group); omit it to create under this server's own
    authenticated identity."""
    _require_provider(provider)
    if provider == "github":
        return _github_create_repo(name, owner, private, description)
    return _gitlab_create_repo(name, owner, private, description)


@mcp_server.tool()
async def fork_repository(
    provider: Provider, owner: str, repo: str, target_owner: Optional[str] = None
) -> Dict[str, Any]:
    """Fork a repository. `target_owner` forks into a specific organization/
    namespace; omit it to fork into this server's own authenticated identity."""
    _require_provider(provider)
    if provider == "github":
        return _github_fork_repo(owner, repo, target_owner)
    return _gitlab_fork_repo(owner, repo, target_owner)


@mcp_server.tool()
async def delete_repository(provider: Provider, owner: str, repo: str) -> Dict[str, Any]:
    """ALWAYS refuses - this server never deletes a repository, on either
    provider. Returns the manual deletion steps instead (ADR-0120)."""
    _require_provider(provider)
    return {
        "refused": True,
        "reason": (
            "Repository deletion is a deliberately unsupported destructive "
            "operation for this MCP server (ADR-0120) - it is never "
            "performed automatically, regardless of caller or credentials."
        ),
        "provider": provider,
        "repository": f"{owner}/{repo}",
        "manual_instructions": _DELETE_INSTRUCTIONS[provider],
    }


class GatewayTokenMiddleware(BaseHTTPMiddleware):
    """ADR-0037 workload-identity check, ahead of any MCP protocol handling
    (identical pattern to every other server in components/mcp-servers/)."""

    async def dispatch(self, request: Request, call_next):
        caller_token = request.headers.get("x-zuno-gateway-token", "")
        if not GATEWAY_WORKLOAD_TOKEN or not hmac.compare_digest(caller_token, GATEWAY_WORKLOAD_TOKEN):
            return JSONResponse({"detail": "missing or invalid X-Zuno-Gateway-Token"}, status_code=401)
        return await call_next(request)


mcp_asgi_app: ASGIApp = mcp_server.streamable_http_app(
    streamable_http_path="/mcp",
    transport_security=TransportSecuritySettings(
        allowed_hosts=os.getenv(
            "MCP_ALLOWED_HOSTS",
            "git-forge-mcp.zuno-ai-run.svc:8000,"
            "git-forge-mcp.zuno-ai-run.svc.cluster.local:8000,"
            "git-forge-mcp:8000,localhost:8000,127.0.0.1:8000",
        ).split(","),
    ),
)
mcp_asgi_app.add_middleware(GatewayTokenMiddleware)
app.mount("/", mcp_asgi_app)
