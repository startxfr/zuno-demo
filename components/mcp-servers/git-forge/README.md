# MCP server: git-forge

Zuno's first multi-provider external MCP integration: one real MCP server
fronting BOTH GitHub (`PyGithub`) and GitLab (`python-gitlab`), selected
per call via an explicit `provider: "github" | "gitlab"` tool argument
(ADR-0120), rather than deploying one server per platform.

Eight capabilities (`git.*`, ADR-0116 naming), exposed here as:

| Tool | Capability | Does |
|---|---|---|
| `read_repository_content` | `git.repository.read` | Read a file's content or list a directory in a **public** repo (either provider) |
| `read_private_repository_content` | `git.repository.private.read` | Same, but allows private/internal too - **GitLab only** |
| `list_repositories` | `git.repository.list` | List a user's/organization's (GitHub) or user's/group's (GitLab) **public** repositories |
| `list_private_repositories` | `git.repository.private.list` | Same, but includes private/internal too - **GitLab only** |
| `write_file` | `git.file.write` | Create or update a file as a single commit - **public repos only**, either provider |
| `create_repository` | `git.repository.create` | Create a new repository |
| `fork_repository` | `git.repository.fork` | Fork a repository |
| `delete_repository` | `git.repository.delete` | **Always refuses** - see below |

## Visibility is a server-enforced rule, not a policy-only one (ADR-0121)

`read_repository_content`/`list_repositories`/`write_file` refuse (or
filter out) private content on **either** provider, unconditionally -
this server has no per-caller identity to check (service-identity auth,
by design), so it can't tell Tekos from Arkos, and doesn't try to. What
it enforces instead is a hard invariant: those three tools never touch
private content for anyone. Private access exists only through
`read_private_repository_content`/`list_private_repositories`, and only
for GitLab (`provider="github"` is refused outright by both - this server
never grants private GitHub access to anyone, through any tool).

Which *agent* can reach the private-scoped tools at all is still governed
the normal way - OKF `allowed_tools` intersected with
`policies/tools/tool-policy.yaml` (ADR-0011). E.g. Arkos declares
`git.repository.private.read`/`.list`, Tekos doesn't.

## `delete_repository` always refuses

This is a deliberate product decision (ADR-0120), not a missing feature.
`delete_repository` never instantiates a GitHub/GitLab client and never
makes a network call - it unconditionally returns a structured refusal
plus the manual steps for the given provider (repo Settings > Danger
Zone / Advanced > Delete, or the provider's own DELETE API endpoint with
elevated scope/role). No authorization bug anywhere else in this server
can turn into a real deletion, because the code path that would need to
exist for that to happen simply isn't there.

As defense in depth, the operator-provisioned credentials for this server
must also never be granted deletion rights:

- **GitHub**: the fine-grained PAT must NOT include the `delete_repo`
  scope.
- **GitLab**: the account behind the PAT must NOT have the Owner role on
  any project this server can reach (Developer/Maintainer is enough for
  read/write/create/fork).

This server cannot introspect its own token's granted scopes before the
provider itself would reject a call needing them - the constraint is
enforced by how the credential is provisioned in Vault, not by this
server's code.

## Transport and auth

Transport: a real, standards-compliant MCP server - the official `mcp`
Python SDK's `MCPServer`, streamable-HTTP transport, mounted at `POST /mcp`
- same shape as every other server in `components/mcp-servers/`. The
gateway remains the trust boundary; this server does not re-validate the
caller's end-user JWT. Every `/mcp` call must also carry
`X-Zuno-Gateway-Token`, a shared secret only the gateway holds.

**Authentication mode: `service-identity`** (ADR-0208). One shared
technical identity per provider:

- `GITHUB_TOKEN`, sourced from an `ExternalSecret` resolving
  `zuno/github/technical` (key `token`).
- `GITLAB_TOKEN` + `GITLAB_BASE_URL`, sourced from an `ExternalSecret`
  resolving `zuno/gitlab/technical` (keys `token`/`url` - `url` supports a
  self-managed GitLab instance; defaults to `https://gitlab.com`).

A call for a provider whose token isn't configured fails with a clear
config error at call time - the server does not require both providers to
be configured to start serving the one that is.

`GET /healthz` checks that at least one of `GITHUB_TOKEN`/`GITLAB_TOKEN` is
configured; it deliberately does **not** make a live GitHub/GitLab call on
every probe - a Kubernetes liveness/readiness probe firing every ~10-15s
against a real external SaaS API would be a needless, avoidable load/quota
cost.

See `server.py`, `Dockerfile`, `requirements.txt`,
`tests/test_mcp_protocol.py` (exercises the real MCP SDK client against
this server's ASGI app, with GitHub/GitLab themselves mocked). Deployed by
`gitops/charts/mcp-git-forge` in the `zuno-ai-run` namespace, matching
`components/mcp-gateway`'s binding registry endpoint
(`http://git-forge-mcp.zuno-ai-run.svc:8000`).
