# ADR-0120: Implement a multi-provider Git-forge MCP server for GitHub and GitLab

- **Status:** Partially implemented - see `components/mcp-servers/git-forge/`. Server, bindings, policy, chart and protocol tests merged; all repo-provable acceptance criteria pass (protocol tests, bindings/policy coverage, chart lint, conformance/hardening checks). Live GitHub/GitLab Cloud verification and PAT provisioning are an operator follow-up (WP-058), same split ADR-0117 used for Confluence.
- **Target:** v0.1
- **Date:** 2026-08-19
- **Decision owners:** Zuno Demo architecture team

## Context

No GitHub/GitLab integration exists in this repo. The business need: read
public and private repository content, write to a repository, create a
repository, fork a repository, list a user's or organization's
repositories, and refuse repository deletion while explaining how to do
it manually per platform. ADR-0116's target catalogue (Confluence, Jira,
Drive, Gmail, Salesforce, Calendar, Meet, Workday) does not name either
platform - this ADR introduces `git.*` as a new logical domain.

Both official vendor MCP servers were evaluated and rejected as-is:
GitHub's official server (`github/github-mcp-server`, Go, MIT) exposes a
real `delete_repository` tool, incompatible with the refusal requirement.
GitLab's official server covers issues/MRs/pipelines but no repository
create/fork/delete/list at all. A community GitLab server does support a
policy-controlled delete-blocking mode, but is Node/TypeScript - adopting
it would break every convention this repo's MCP servers share (per-
component Python venv, the gateway-token middleware, the Vault
ExternalSecret shape, `helm template`-based hardening checks). This ADR
instead builds a server on this repo's own template (ADR-0119's
scaffolding), using the `PyGithub`/`python-gitlab` client libraries -
reusing well-maintained API clients, not reusing MCP servers.

## Decision

One new component, `components/mcp-servers/git-forge/` (chart
`gitops/charts/mcp-git-forge/`, image `mcp-git-forge`, service
`git-forge-mcp.zuno-ai-run.svc:8000`), implementing six logical
capabilities under the `git.*` domain (`<domain>.<resource>.<verb>`,
ADR-0116). Per this project's earlier decision to build a single
multi-provider server rather than one server per platform, every tool
takes an explicit `provider: "github" | "gitlab"` argument, dispatched
internally to a `PyGithub` or `python-gitlab` client:

| Capability | Tool | Covers |
|---|---|---|
| `git.repository.read` | `read_repository_content` | read file/directory content, public and private |
| `git.repository.list` | `list_repositories` | list a user's or organization's/group's repositories |
| `git.file.write` | `write_file` | create-or-update a file as one commit |
| `git.repository.create` | `create_repository` | create a repository |
| `git.repository.fork` | `fork_repository` | fork a repository |
| `git.repository.delete` | `delete_repository` | **always refused** |

**`delete_repository` is refused by construction, not by policy.** Its
implementation never instantiates a GitHub/GitLab client and never makes
a network call - it unconditionally returns a structured refusal plus the
provider-specific manual steps (repo Settings > Danger Zone / Advanced >
Delete, or the provider's own DELETE endpoint with elevated scope/role).
No authorization bug elsewhere in this server can turn into a real
deletion, because the code path that would perform one does not exist.
As defense in depth, the operator-provisioned service credentials must
also never carry deletion rights: the GitHub PAT must not include the
`delete_repo` scope, and the GitLab account must not hold the Owner role
on any reachable project.

Authentication mode is `service-identity` (ADR-0208): two independent
Vault-sourced credentials, `zuno/github/technical` (`token`) and
`zuno/gitlab/technical` (`token`, `url` - supports a self-managed
instance, defaults to `https://gitlab.com`), each its own `ExternalSecret`
(independent rotation). `requirements.txt` pins `PyGithub==2.9.1` and
`python-gitlab==8.5.0` alongside this repo's usual `fastapi`/`uvicorn`/
`mcp` base. Built via ADR-0119's scaffolding/conformance tooling - the
first real consumer of both, same role Confluence played proving
ADR-0116's binding registry.

## Consequences

Zuno gains its first multi-provider external MCP integration and its
first `git.*` capabilities. These are also the first capabilities in this
domain to carry create/write/fork privilege, not just read - no agent's
OKF tasks declare any of the six today, so every initial call denies on
the ADR-0011 agent_declaration factor, the same initial state Confluence's
write capabilities had at WP-02 (expected, not a defect).

## Security considerations

Read/write capability separation (ADR-0340) applies: `git.repository.read`/
`git.repository.list` are logically distinct from `git.file.write`/
`git.repository.create`/`git.repository.fork`, and an OKF task must
declare each it needs rather than inheriting write from read.
`git.repository.delete` stays a normal, policy-gated capability (not
special-cased to bypass authorization) so an unauthorized caller is
denied by the ordinary intersection and an authorized one receives the
server's explanation rather than "unknown tool" - but, per the Decision
above, no caller of any authorization level can make it actually delete
anything.

## Operational considerations

`read_repository_content`/`list_repositories` must page explicitly against
GitHub's rate limits (5000 req/h authenticated) rather than looping
naively over large repositories/organizations. `/healthz` does not call
GitHub/GitLab on every probe (same reasoning as every other server in
this repo) and passes once at least one of the two provider tokens is
configured - the other provider then fails clearly at call time instead
of the whole server refusing to start.

## Acceptance criteria

- All six `git.*` capabilities execute against real GitHub/GitLab Cloud
  through the gateway, for both `provider` values (operator follow-up).
- `delete_repository` never issues a DELETE call regardless of caller or
  provider - proven by a dedicated negative test that fails the test
  itself if `_github_client`/`_gitlab_client` is even constructed.
- The GitHub PAT provisioned in Vault carries no `delete_repo` scope; the
  GitLab account provisioned in Vault does not hold Owner on any
  reachable project (operator-verified, not code-enforced).
- Agent Runtime/OKF carry no GitHub/GitLab URL, credential, or vendor
  tool name - only the six logical `git.*` capability IDs.
- `components/mcp-servers/git-forge/tests/test_mcp_protocol.py` covers
  the MCP protocol surface (tools/list, the gateway-token 401 path) and
  each tool's request/response mapping against mocked GitHub/GitLab
  clients.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0010](0010-introduce-a-central-mcp-gateway.md)
- [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md)
- [ADR-0024](0024-use-vault-for-application-secrets.md)
- [ADR-0043](0043-use-standard-mcp-protocol-behind-the-zuno-mcp-gateway.md)
- [ADR-0116](0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md)
- [ADR-0117](0117-implement-confluence-as-the-first-real-external-mcp-integration.md)
- [ADR-0119](0119-introduce-mcp-server-scaffolding-and-conformance-tooling.md)
- [ADR-0208](0208-standardize-enterprise-tool-authentication-and-delegation.md)
- [ADR-0340](0340-extend-business-role-authorization-with-cdp-and-scoped-capabilities.md)
