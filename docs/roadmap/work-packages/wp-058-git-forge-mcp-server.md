# WP-058: Git-forge MCP server (GitHub + GitLab)

- **State:** Operator pending (repo work merged 2026-08-19)
- **ADRs:** ADR-0120 (To be implemented -> Partially implemented)
- **Depends on:** WP-057 (merged)
- **Blocks:** none
- **Estimated files touched:** ~20

> Execute this brief as a standalone task from the repository root. Read the
> referenced ADR sections before editing. If the repository state contradicts
> a step, stop and report instead of improvising.

## Goal

Build the first multi-provider external MCP integration: a git-forge MCP
server in `components/mcp-servers/git-forge/` implementing the six
`git.*` capabilities ADR-0120 decides, using ADR-0119's scaffolding as its
starting point. Repo work lands everything except live GitHub/GitLab
Cloud verification and PAT provisioning (operator steps).

## ADR references

Primary: [docs/adr/0120-implement-a-multi-provider-git-forge-mcp-server-for-github-and-gitlab.md](../../adr/0120-implement-a-multi-provider-git-forge-mcp-server-for-github-and-gitlab.md)

Acceptance criteria: the six `git.*` capabilities execute against real
GitHub/GitLab Cloud through the gateway for both `provider` values;
`delete_repository` never issues a DELETE call regardless of caller or
provider (proven by a test that fails if a client is even constructed);
the provisioned GitHub PAT carries no `delete_repo` scope and the GitLab
account holds no Owner role (operator-verified); Agent Runtime/OKF carry
no vendor URL/credential/tool name, only the six logical capability IDs.

Key decisions binding this WP: authentication mode is `service-identity`
(ADR-0208) via two independent Vault credentials
(`zuno/github/technical`, `zuno/gitlab/technical`); `provider` is a tool
argument, not a separate binding per platform (single multi-provider
server); `delete_repository` never instantiates a client (ADR-0120
Decision).

## Preconditions (verify before starting)

- WP-057 merged: `test -f platform/scaffolding/new_mcp_server.py` and
  `test -f platform/supply-chain/check_mcp_server_conformance.py`.
- `python3 platform/docs/check_docs.py` exits 0 (pre-existing, unrelated
  ADR-0212/0214 drift aside - see WP-057's own note).
- Read fully before editing: `components/mcp-servers/confluence/server.py`,
  `gitops/charts/mcp-confluence/` (all templates), `ansible/roles/vault/tasks/install.yml`
  (the `zuno/confluence/technical`/`zuno/salesforce/technical` secret
  shapes), `ansible/confidential.example.yml`, `platform/bindings/tools/tool-bindings.yaml`,
  `policies/tools/tool-policy.yaml`.

## Repo changes (step by step)

1. **Scaffold + implement `components/mcp-servers/git-forge/`**: generated
   via `make new-mcp-server NAME=git-forge`, then hand-edited for the real
   multi-provider shape - `server.py` (six tools dispatching to
   `PyGithub`/`python-gitlab` by an explicit `provider` argument;
   `delete_repository` never instantiates either client), `requirements.txt`
   (`PyGithub==2.9.1`, `python-gitlab==8.5.0`), `Dockerfile`, `README.md`,
   `tests/test_mcp_protocol.py` (protocol tests against mocked GitHub/GitLab
   clients, including a dedicated negative test for the delete refusal).
2. **Bindings:** in `platform/bindings/tools/tool-bindings.yaml`, add a
   `backends: git-forge` default endpoint block (ADR-0119's shorthand -
   first real use) and six `git.*` capability entries pointing at it.
3. **Policy:** in `policies/tools/tool-policy.yaml`, add six matching
   entries (`mcp_server: git-forge`, `min_classification: C2`,
   `allowed_groups: [consultant, board, cdp]` - same groups as Confluence's
   own entries).
4. **Chart + GitOps:** `gitops/charts/mcp-git-forge/` mirroring
   `gitops/charts/mcp-confluence/`, but with TWO ExternalSecrets (one per
   provider - `zuno/github/technical`, `zuno/gitlab/technical`) feeding
   `GITHUB_TOKEN`/`GITLAB_TOKEN`/`GITLAB_BASE_URL`; `gitops/apps/mcp-git-forge/`
   Application pair mirroring `gitops/apps/mcp-confluence/`.
5. **Vault seeding:** two new tasks in `ansible/roles/vault/tasks/install.yml`
   (`zuno/github/technical`, `zuno/gitlab/technical`), documented in
   `ansible/confidential.example.yml`. No build/CI wiring needed - WP-057's
   `discover-mcp-servers` job picks up `components/mcp-servers/git-forge/Dockerfile`
   automatically.
6. **Hardening registration:** add `mcp-git-forge` to
   `platform/security/check_workload_hardening.py`'s `DEPLOYMENT_CHARTS`
   and NetworkPolicy coverage loop, and a "git-forge MCP server tests" step
   to `.github/workflows/lint.yml`'s python job (`check_mcp_server_conformance.py`
   fails otherwise - verified during this WP).

## What NOT to touch

- Decision text of any existing ADR.
- `gitops/apps/*` `targetRevision` values; chart `image.tag` policy (WP-04).
- `ansible/confidential.yml` (gitignored, operator-owned - only its
  `.example.yml` template is repo content).
- Any file another concurrent session is actively editing - re-check
  `git status` before staging (this repo runs parallel sessions).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m py_compile components/mcp-servers/git-forge/server.py`
- `cd components/mcp-servers/git-forge && .venv/bin/python3 tests/test_mcp_protocol.py`
  (all 15 pass, including both delete-refusal negative tests - verified
  against the real installed `PyGithub`/`python-gitlab` 2.9.1/8.5.0, not
  just mocked interfaces)
- `cd components/mcp-gateway && .venv/bin/python3 tests/test_bindings.py`
  (real-registry coverage tests pass with the six new `git.*` entries)
- `python3 platform/supply-chain/check_mcp_server_conformance.py` → `RESULT: PASS`
- `python3 platform/supply-chain/check_build_matrix.py` → `RESULT: PASS`
  (git-forge built via WP-057's discovery job, zero manual matrix entry)
- `python3 platform/security/check_workload_hardening.py` → `RESULT: PASS`
- `helm lint gitops/charts/mcp-git-forge` and `helm template` renders
  cleanly
- `python3 platform/docs/check_docs.py` - same pre-existing, unrelated
  ADR-0212/0214 drift as WP-057; no new drift from this WP's own changes

## Operator / human follow-up (not executable by the model)

1. Operator: create a GitHub fine-grained PAT (Contents read/write,
   Administration write for `create_repository`; **no** `delete_repo`
   scope) and store it at `zuno/github/technical` in Vault (or via
   `ansible/confidential.yml` + `make day0 install vault`).
2. Operator: create a GitLab PAT (`api` scope) for a Developer/Maintainer
   account (**not** Owner) and store it (with `url` if self-managed) at
   `zuno/gitlab/technical`.
3. Operator: deploy and run `make d1 build mcp` then `make d1 install mcp`;
   verify the six capabilities execute against real GitHub/GitLab Cloud -
   discharges the live-verification acceptance bullet.
4. Operator: run one end-to-end chain per provider (public read, private
   read, write, create, fork, delete-refusal) and record trace evidence.

## Status updates (then re-run check_docs.py)

- After repo merge: ADR-0120 body `- **Status:**` → already
  `Partially implemented` in this change; `docs/adr/README.md` ADR-0120
  row → already `Partially implemented`; this file's State line → already
  `Operator pending`.
- After operator steps: ADR-0120 → `Implemented - see \`components/mcp-servers/git-forge/\`.`;
  index row → `Implemented`; tracker row → `Done`; this file's State line
  → `Done`; `MEMORY.md` dated bullet.

## Out of scope / deferred

- Any agent's OKF tasks declaring `git.*` capabilities - this WP only
  makes the capability available (mirrors Confluence's initial
  all-deny-until-declared state at WP-02); a future WP wires a specific
  agent to it once one needs it.
- GitHub App / delegated-user OAuth auth mode (rejected for now per the
  earlier arbitration - PAT/service-identity only).
- A shared web-search-style summary/diff tool across providers - each of
  the six tools stays a thin, explicit per-provider dispatch.
