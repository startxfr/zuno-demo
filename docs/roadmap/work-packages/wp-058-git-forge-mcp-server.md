# WP-058: Git-forge MCP server (GitHub + GitLab)

- **State:** Done (repo work merged 2026-08-19; operator deploy + live verification 2026-08-23)
- **ADRs:** ADR-0120 (To be implemented -> Partially implemented -> Implemented)
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

1. ~~Operator: create a GitHub fine-grained PAT...~~ Done - `zuno/github/technical`
   seeded from `ansible/confidential.yml` via `make day0 install vault`
   (2026-08-23).
2. ~~Operator: create a GitLab PAT...~~ Done - `zuno/gitlab/technical` seeded
   the same way (`url` left at the `https://gitlab.com` default).
3. Deploy: **`make day2 build mcp` then `make day2 install mcp`** (mcp
   moved Day1→Day2 under ADR-0060, 2026-08-22 - this step's commands were
   stale). Run 2026-08-23; `zuno-mcp-git-forge-d0`/`-d1` reached
   Synced/Healthy in `zuno-ai-run`.
4. Live verification run 2026-08-23, scope **read + delete-refusal only**
   (write/create/fork deliberately excluded - would have created real
   repos/commits on GitHub.com/GitLab.com under the technical account;
   those three stay verified by `tests/test_mcp_protocol.py` only, not
   live). Exercised directly against the git-forge MCP endpoint
   (`http://git-forge-mcp.zuno-ai-run.svc:8000/mcp`) with the real MCP
   SDK client and the gateway workload token, from inside the pod:
   - `read_repository_content`/`list_repositories` - both providers, live,
     pass (`octocat/Hello-World`, `octocat`'s repos; `gitlab-org/gitlab`,
     `gitlab-org`'s repos).
   - `read_private_repository_content`/`list_private_repositories` -
     GitLab, live, pass; GitHub correctly refuses (ADR-0121 guard).
   - `delete_repository` - both providers, live, correctly refuses with
     manual instructions, never constructs a client.

   This run caught and fixed two real, live-only bugs (neither visible to
   the existing mocked test suite or to any prior repo-only check):
   - `components/mcp-servers/git-forge/server.py`'s `_github_client()`
     passed a `float` timeout to PyGithub 2.9.1's `Github(...)`, which
     asserts `isinstance(timeout, int)` - every GitHub call failed at
     construction time. Fixed with an `int()` cast; added
     `test_github_client_constructs_without_mocking` (exercises the real,
     unmocked factory) so a regression fails the test suite next time.
   - `ansible/tasks/apply_openshift_build.yml`'s force-fresh-build task
     only checked `day1_verb`, never `day2_verb` - `make day2 build
     <component>` (used by `mcp`, `rag`, `rag-ingestion`, `agent`, `mlops`
     since ADR-0060) silently never forced a real rebuild, always
     re-verifying whatever Build already existed. Fixed by checking both
     verbs, matching the pattern the signing step below it already used.

## Status updates (then re-run check_docs.py)

- After repo merge: ADR-0120 body `- **Status:**` → already
  `Partially implemented` in this change; `docs/adr/README.md` ADR-0120
  row → already `Partially implemented`; this file's State line → already
  `Operator pending`.
- After operator steps (done 2026-08-23): ADR-0120 →
  `Implemented - see \`components/mcp-servers/git-forge/\`.` (noting
  write/create/fork are protocol-test-verified only, not live); index row
  → `Implemented`; tracker row → `Done`; this file's State line → `Done`.

## Out of scope / deferred

- Any agent's OKF tasks declaring `git.*` capabilities - this WP only
  makes the capability available (mirrors Confluence's initial
  all-deny-until-declared state at WP-02); a future WP wires a specific
  agent to it once one needs it.
- GitHub App / delegated-user OAuth auth mode (rejected for now per the
  earlier arbitration - PAT/service-identity only).
- A shared web-search-style summary/diff tool across providers - each of
  the six tools stays a thin, explicit per-provider dispatch.
