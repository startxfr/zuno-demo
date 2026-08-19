# ADR-0121: Restrict git-forge write and private access by visibility

- **Status:** Implemented - see `components/mcp-servers/git-forge/server.py`, `agents/tekos/tasks/answer-technical-question.md`, `agents/arkos/tasks/draft-architecture-testimonial.md`.
- **Target:** v0.1
- **Date:** 2026-08-20
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0120 shipped six `git.*` capabilities but no agent declared any of
them yet. The first two real consumers need genuinely different
privilege: Tekos gets read-only access to public repositories on both
GitHub and GitLab; Arkos gets to create repositories, read existing ones,
and commit - but commits must only ever land in public repositories, and
its read reach extends to private repositories on GitLab only, never
GitHub.

The existing six capabilities can't express this. `git.repository.read`/
`git.file.write` have no visibility (public/private) concept - they let
whichever shared service credential is configured read/write whatever it
can reach, identically for every caller. That's a direct consequence of
`service-identity` auth (ADR-0208): one shared GitHub PAT and one shared
GitLab PAT for every caller, with the MCP Gateway authorizing the caller
*before* either credential is used - `components/mcp-servers/git-forge`
itself has no per-caller identity to check, by design (same as every
other `service-identity` server in this repo). So the only way to give
Arkos strictly more reach than Tekos through those same shared
credentials is to split the capability itself - the same move ADR-0340
already made for Workday (`profile.self.read` vs `profile.any.read`)
instead of parameterizing one tool and trusting a gateway-level check
that can't actually evaluate "is this specific repo public" without an
extra round trip the gateway has no reason to make.

## Decision

Two new capabilities, GitLab-only, additive on top of the existing six:

- `git.repository.private.read` (`read_private_repository_content`) -
  same shape as `read_repository_content`, but allows non-public repos.
- `git.repository.private.list` (`list_private_repositories`) - same
  shape as `list_repositories`, but does not filter out non-public
  entries (returns public *and* private/internal, not "only private" -
  the name is a capability qualifier, not a filter).

Both refuse outright (`ValueError`, before any client is even
constructed for the read case) if called with `provider="github"` - this
server never grants private GitHub access, to any agent, through any
tool. That's a hard, unconditional rule, not a per-caller one.

The three existing capabilities that touch content are tightened to
match, server-side, unconditionally, for every caller:

- `read_repository_content` - refuses if the target repo is private, on
  either provider.
- `list_repositories` - filters results to public-visibility entries
  only, both providers.
- `write_file` - refuses if the target repo is private, on either
  provider (Arkos's "commit only into public repos" - not
  provider-dependent, deliberately stricter than its read reach).

This is enforced in `server.py`, the same code-level-guard style
`delete_repository` already established (ADR-0120) - not left to policy,
because the server is the only party in this chain that actually knows a
given repo's live visibility (GitHub's `.private` / GitLab's
`.visibility`, both already fetched as part of the existing lookup calls,
no extra API round trip). Which *agent* can reach the private-scoped
tools at all is still the ordinary two-layer split this repo always
uses: OKF `allowed_tools` (agent_declaration) intersected with
`policies/tools/tool-policy.yaml` (platform_policy), per ADR-0011. Only
`agents/arkos/tasks/draft-architecture-testimonial.md` declares
`git.repository.private.read`/`.list`; Tekos does not.

`create_repository`/`fork_repository`/`delete_repository` are unchanged
- no visibility restriction was requested for repository creation
itself, and fork/delete are unused by either agent (`delete_repository`
refuses unconditionally regardless of who calls it, per ADR-0120).

Wired consumers, both via their existing primary task (no new task
files):

| Agent | Task | New `allowed_tools` |
|---|---|---|
| Tekos | `answer-technical-question` | `git.repository.read`, `git.repository.list` |
| Arkos | `draft-architecture-testimonial` | `git.repository.read`, `git.repository.list`, `git.repository.private.read`, `git.repository.private.list`, `git.file.write`, `git.repository.create` |

`gitops/charts/arkos/values.yaml`'s `toolCapabilities:` (feeding the
generated `agents/arkos/deployment/aiagent-snapshot.yaml`, CR-managed)
mirrors Arkos's task declaration. Tekos has no equivalent CR/snapshot
dependency. Both OKF schema files'
(`platform/okf/schema/zuno-okf-{task,tool}-v0.2.schema.json`)
`allowed_tools`/`capability` enums gained the six newly-used `git.*` IDs,
matching this repo's established keep-the-enum-in-sync convention (not
mechanically enforced, but every prior capability domain kept it
current).

## Consequences

Tekos and Arkos are the first two agents that actually reach
`git-forge` - every call previously denied on the ADR-0011
agent_declaration factor now resolves for the tools each declares.
Tekos ends up read-only, public-only, both providers. Arkos ends up
able to create/read/write, with write always public-only and its extra
read reach (private) capped to GitLab specifically - exactly the
asymmetric shape requested, expressed entirely through which
capabilities each task declares, with the provider/visibility
invariants enforced once, centrally, in the server, so a third agent
added later can't accidentally get broader reach than intended just by
declaring the wrong tool name.

## Security considerations

The public/private split is enforced unconditionally in `server.py`,
independent of caller - this is intentional defense in depth, not a gap:
even if a future policy/OKF misconfiguration granted some agent
`git.repository.read`, that agent still could not read a private GitHub
repo through it, because the tool itself refuses before making the
provider call. Read/write separation (ADR-0340) still applies on top:
`git.file.write`/`git.repository.create` are declared independently of
the read capabilities, never implied by them.

## Operational considerations

`platform/okf/generate_authorization_matrix.py tekos arkos` and
`platform/okf/generate_deployment_snapshot.py` (Arkos only) were
re-run after the task/values.yaml changes and must be re-run again for
any future `allowed_tools` change to either agent - both are `--check`-
gated in `.github/workflows/lint.yml`'s `policy-as-code` job.

## Acceptance criteria

- `components/mcp-servers/git-forge/tests/test_mcp_protocol.py` proves,
  against both providers: the two new private-scoped tools work for
  GitLab and refuse GitHub; `read_repository_content`/`write_file`
  refuse private repos; `list_repositories` filters private entries out;
  `list_private_repositories` includes them.
- `python3 platform/supply-chain/validate_okf_bundle.py agents/tekos agents/arkos`
  passes (cross-references `allowed_tools` against
  `policies/tools/tool-policy.yaml`, which already carries the two new
  entries from this ADR).
- `python3 platform/okf/generate_authorization_matrix.py --check --all`
  and `python3 platform/okf/generate_deployment_snapshot.py --check`
  pass for tekos/arkos (pre-existing, unrelated drift on
  advantage/comage/finage's own snapshots is out of this ADR's scope -
  same class of gap WP-057/058 already flagged for ADR-0212/ADR-0214).
- The regenerated `agent.okf.md` authorization-matrix tables for both
  agents show exactly the intended row set: Tekos gets `git.repository.read`/
  `.list` only; Arkos gets all six, including both private-scoped ones.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered and Review evidence.

## Related ADRs

- [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md)
- [ADR-0116](0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md)
- [ADR-0120](0120-implement-a-multi-provider-git-forge-mcp-server-for-github-and-gitlab.md)
- [ADR-0208](0208-standardize-enterprise-tool-authentication-and-delegation.md)
- [ADR-0340](0340-extend-business-role-authorization-with-cdp-and-scoped-capabilities.md)
- [ADR-0503](0503-make-each-okf-bundle-state-its-complete-authorization-contract.md)
