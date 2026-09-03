# WP-057: MCP server scaffolding and conformance tooling

- **State:** Done (2026-08-19)
- **ADRs:** ADR-0119 (To be implemented -> Implemented)
- **Depends on:** WP-01 (merged)
- **Blocks:** WP-058
- **Estimated files touched:** ~11

> Execute this brief as a standalone task from the repository root. Read the
> referenced ADR sections before editing. If the repository state contradicts
> a step, stop and report instead of improvising.

## Goal

Replace hand-copying `components/mcp-servers/confluence` for each new MCP
server with a generator + a blocking conformance check, and remove three of
the six manual per-server registration steps (build matrix, ansible build
role) by making them discover servers instead of listing them.

## ADR references

Primary: [docs/adr/0119-introduce-mcp-server-scaffolding-and-conformance-tooling.md](../../adr/0119-introduce-mcp-server-scaffolding-and-conformance-tooling.md)

Acceptance criteria: a new server can be scaffolded with `make new-mcp-server
NAME=<name>`; `check_mcp_server_conformance.py` fails on a missing
gateway-token middleware/healthz/DNS-rebinding-protection or on a chart not
registered in `check_workload_hardening.py`/`lint.yml`; `components/mcp-servers/*/Dockerfile`
is built without a hand-listed `build-publish.yml` matrix entry.

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- Read fully before editing: `components/mcp-servers/confluence/server.py`,
  `gitops/charts/mcp-confluence/` (all templates), `gitops/apps/mcp-confluence/`,
  `components/mcp-gateway/app/bindings.py`, `platform/security/check_workload_hardening.py`,
  `platform/supply-chain/check_build_matrix.py`, `.github/workflows/build-publish.yml`,
  `.github/workflows/lint.yml`, `ansible/roles/mcp_build/tasks/build.yml`.

## Repo changes (step by step)

1. **`platform/scaffolding/new_mcp_server.py`**: generates the confluence-shaped
   template (single default credential, one placeholder tool) into
   `components/mcp-servers/<name>/`, `gitops/charts/mcp-<name>/`,
   `gitops/apps/mcp-<name>/`. Refuses to overwrite existing files without
   `--force`. Add the `make new-mcp-server NAME=<name> [DESCRIPTION="..."]`
   target.
2. **`platform/supply-chain/check_mcp_server_conformance.py`**: discovers
   `components/mcp-servers/*/server.py`, checks for the gateway-token
   middleware/healthz/`TransportSecuritySettings`/`mcp==` pin/Dockerfile
   `ARG BASE_IMAGE` pattern, and cross-checks registration in
   `check_workload_hardening.py`'s `DEPLOYMENT_CHARTS` + NetworkPolicy loop
   and in `lint.yml`'s python job. Wire as a blocking step in `lint.yml`.
3. **Discovery-driven build matrix**: add a `discover-mcp-servers` job to
   `build-publish.yml` (globs `components/mcp-servers/*/Dockerfile`) feeding
   a `build-publish-sign-mcp-servers` matrix job; remove the three
   hand-listed `mcp-sales-db`/`mcp-confluence`/`mcp-salesforce` entries from
   the main matrix. Update `check_build_matrix.py` to exclude
   `components/mcp-servers/*/Dockerfile` from the static-matrix-orphan check
   and instead verify the discovery job still targets that directory.
   Replace `ansible/roles/mcp_build/tasks/build.yml`'s three per-server
   `include_tasks` blocks with an `ansible.builtin.find` + loop.
4. **`backends:` endpoint defaults**: extend `platform/bindings/tools/tool-bindings.yaml`'s
   schema (documented in `platform/bindings/tools/README.md`) and
   `components/mcp-gateway/app/bindings.py`'s loader/validator with an
   optional top-level `backends:` map consulted only when an entry omits its
   own `endpoint:`. No existing entry changes.
5. **Fix the two real gaps the new conformance check found**: add
   `mcp-salesforce` to `check_workload_hardening.py`'s NetworkPolicy coverage
   loop (it was already in `DEPLOYMENT_CHARTS` but missing there), and add a
   "salesforce MCP server tests" step to `lint.yml`'s python job (the tests
   existed but never ran in CI).

## What NOT to touch

- Decision text of any existing ADR.
- `gitops/apps/*` `targetRevision` values; chart `image.tag` policy (WP-04).
- Any file another concurrent session is actively editing - re-check
  `git status` before staging (this repo runs parallel sessions).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m py_compile platform/scaffolding/new_mcp_server.py platform/supply-chain/check_mcp_server_conformance.py components/mcp-gateway/app/bindings.py`
- `python3 platform/supply-chain/check_mcp_server_conformance.py` → `RESULT: PASS`
- `python3 platform/supply-chain/check_build_matrix.py` → `RESULT: PASS`
- `python3 platform/security/check_workload_hardening.py` → `RESULT: PASS`
- `cd components/mcp-gateway && .venv/bin/python3 tests/test_bindings.py` (all pass, including the two new `backends:` tests)
- `make new-mcp-server` (no NAME) exits non-zero with a usage message; a real
  invocation followed by `helm lint`/`py_compile` on the generated output
  succeeds (verified manually during this WP, output discarded - it is not
  a real server).
- `python3 platform/docs/check_docs.py` - pre-existing, unrelated failure at
  the time of this WP: ADR-0212/ADR-0214 status drift (index says
  `Proposed`, ADR body says `Implemented`) - a different, concurrently
  in-flight change owns that, not this WP. This WP's own additions
  (ADR-0119/ADR-0120 index rows) introduce zero new drift findings.

## Operator / human follow-up

None. This WP is fully provable from the repository - `build-publish.yml`'s
own dynamic matrix is unexecutable in this sandbox (no live GitHub Actions
runner), same honest scope as every other workflow change in this repo, but
it is validated by YAML/schema inspection and `check_build_matrix.py`.

## Status updates (then re-run check_docs.py)

- `docs/adr/0119-introduce-mcp-server-scaffolding-and-conformance-tooling.md`:
  already recorded `Implemented` in this change (repo-provable, no operator
  step needed).
- `docs/adr/README.md`: ADR-0119 row → `Implemented` (already done).
- `docs/roadmap/implementation-roadmap.md`: WP-057 tracker row →
  `Done`.
- This file: `- **State:**` → `Done` (already reflects this).
- `MEMORY.md`: one dated bullet describing the scaffolding/conformance
  tooling as implemented.

## Out of scope / deferred

- The git-forge MCP server itself consuming this tooling (WP-058).
- A shared Python runtime library across MCP servers - deliberately rejected
  in ADR-0119 (fights the per-component venv isolation this repo relies on).
