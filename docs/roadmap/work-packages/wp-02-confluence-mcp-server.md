# WP-02: Real Confluence MCP server

- **State:** Operator pending (2026-08-14 — repo work merged: real MCP server, binding registry wiring, policy entries, chart, build/deploy plumbing, protocol tests. Awaiting real Confluence Cloud credentials + e2e verification; ADR-0043's status-line follow-up is deferred with it, per this brief's Post-operator repo follow-up section.)
- **ADRs:** ADR-0117 (To be implemented -> Partially implemented -> Implemented)
- **Depends on:** WP-01 (merged)
- **Blocks:** WP-25
- **Estimated files touched:** ~10

> Execute this brief as a standalone task from the repository root. Read the
> referenced ADR sections before editing. If the repository state contradicts
> a step, stop and report instead of improvising.

## Goal

Build the first real external MCP integration: a Confluence MCP server in
`components/mcp-servers/confluence/` implementing the four ADR-0116
capabilities, resolved through WP-01's binding registry, replacing the
demo-mode handler. Repo work lands everything except the live Confluence
Cloud verification, which is an operator step.

## ADR references

Primary: [docs/adr/0117-implement-confluence-as-the-first-real-external-mcp-integration.md](../../adr/0117-implement-confluence-as-the-first-real-external-mcp-integration.md)

Acceptance criteria (verbatim from the ADR):

> - `confluence.page.search`/`read`/`create`/`update` execute against real Confluence Cloud through the MCP Gateway, not the demo handler.
> - A task can retrieve `knowledge.tech` context, then separately read a live Confluence page and write/update it, in one exercised chain (extended to `knowledge.project` once ADR-0209 lands in v0.2).
> - Agent Runtime and OKF task definitions contain no Confluence server URL, credential, or vendor-specific tool name - only the four logical capability IDs.
> - `mcp-gateway/app/downstream.py` resolves these capabilities via binding data, not a new hardcoded tool-name entry.
> - An end-to-end acceptance test covers the full chain; the demo-mode Confluence handler is removed once the real implementation passes it.
> - `docs/adr/0043-use-standard-mcp-protocol-behind-the-zuno-mcp-gateway.md`'s status line is updated in place to record Confluence as migrated, once this ADR's acceptance criteria are met (procedural follow-up, not part of this ADR's own decision).

Key decisions binding this WP: authentication mode is `service-identity`
(ADR-0208) using the `zuno/confluence/technical` Vault credential (email +
API token) already provisioned via `ansible/roles/vault/tasks/install.yml`;
`policy.evaluate()` authorizes **before** the shared service identity is used.

## Preconditions (verify before starting)

- WP-01 merged: `test -f components/mcp-gateway/app/bindings.py` and
  `test -f platform/bindings/tools/tool-bindings.yaml`.
- `python3 platform/docs/check_docs.py` exits 0.
- Read fully before editing: `components/mcp-servers/sales-db/server.py`,
  `components/mcp-servers/sales-db/Dockerfile`,
  `components/mcp-servers/sales-db/tests/test_mcp_protocol.py`,
  `components/mcp-gateway/app/handlers/confluence.py` (the demo handler you
  will remove), `ansible/roles/vault/tasks/install.yml` (the
  `zuno/confluence/technical` secret shape), `gitops/charts/mcp-sales-db/`
  (chart precedent), `ansible/roles/mcp_build/` (how MCP server images build).

## Repo changes (step by step)

1. **Create `components/mcp-servers/confluence/`** mirroring
   `components/mcp-servers/sales-db/`'s shape exactly: `server.py`
   (MCP SDK server, gateway-token-authenticated, parameterized tools),
   `requirements.txt`, `Dockerfile` (same base-image pinning style as
   sales-db), `tests/test_mcp_protocol.py`, `README.md` (replace the current
   placeholder README content). Implement exactly four tools mapped to
   `confluence.page.search`, `confluence.page.read`, `confluence.page.create`,
   `confluence.page.update`, calling the Confluence Cloud REST API with
   email + API token read from environment variables sourced from the Vault
   secret (never hard-coded, never logged).
2. **Bindings:** in `platform/bindings/tools/tool-bindings.yaml`, point the
   four `confluence.page.*` capabilities at the new server (transport +
   Service endpoint reference), replacing their in-process demo-handler
   binding. Keep the `search_confluence` alias mapped to
   `confluence.page.search`.
3. **Remove the demo handler**: delete
   `components/mcp-gateway/app/handlers/confluence.py` and its references;
   the gateway must reach Confluence only through the binding-resolved MCP
   server. Update gateway tests accordingly.
4. **Chart + GitOps:** create `gitops/charts/mcp-confluence/` mirroring
   `gitops/charts/mcp-sales-db/` (Deployment/Service, hardened per
   `platform/security/check_workload_hardening.py`, External Secrets wiring
   for `zuno/confluence/technical`), and a `gitops/apps/mcp-confluence/`
   Application mirroring `gitops/apps/mcp-sales-db/`.
5. **Build wiring:** add the new image to `.github/workflows/build-publish.yml`'s
   matrix (required — `platform/supply-chain/check_build_matrix.py` is
   blocking) and to `ansible/roles/mcp_build/` following how the sales-db
   image is built there.
6. **End-to-end acceptance test:** add a gateway-level test (mirroring
   `components/mcp-gateway/tests/test_downstream_sales_db.py`) that mocks the
   Confluence REST API and proves the full chain
   capability → binding → MCP server → (mocked) Confluence, including the
   deny path for an unauthorized caller.

## What NOT to touch

- Decision text of any existing ADR.
- The uncommitted ADR-0344 change set if still present in `git status`.
- `gitops/apps/*` `targetRevision` values; chart `image.tag` policy (WP-04).
  If WP-04 stage 3 has already landed (check whether
  `platform/supply-chain/check_no_latest_tags.py` is blocking in
  `.github/workflows/lint.yml`), the new chart must ship with an immutable
  tag supplied by the operator's release — ask for it rather than writing
  `latest`.
- `knowledge.tech` ingestion (`components/rag-ingestion/`) — read path is
  unchanged by this WP (ADR-0205 split).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m py_compile components/mcp-servers/confluence/server.py`
- `python3 -m pytest components/mcp-servers/confluence/tests/ components/mcp-gateway/tests/ -q`
- `python3 platform/supply-chain/check_build_matrix.py` (exit 0)
- `python3 platform/security/check_workload_hardening.py` (exit 0)
- `helm lint gitops/charts/mcp-confluence`
- `test ! -f components/mcp-gateway/app/handlers/confluence.py`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`
- `! grep -rn "atlassian" agents/` (no vendor names in OKF bundles)

## Operator / human follow-up (not executable by the model)

1. Operator: create/confirm the real Confluence Cloud API token and store it
   at `zuno/confluence/technical` in Vault (email + API token), per
   `ansible/roles/vault/tasks/install.yml`.
2. Operator: deploy and run `make d1 check mcp` (and `make d1 build mcp`
   first if images are built in-cluster); verify the four capabilities
   execute against real Confluence Cloud — discharges acceptance bullets 1
   and 2.
3. Operator: run the end-to-end chain (indexed `knowledge.tech` read, then a
   live page read + update) and record the trace evidence.

## Post-operator repo follow-up

- Update `docs/adr/0043-use-standard-mcp-protocol-behind-the-zuno-mcp-gateway.md`'s
  status line in place to record Confluence as migrated (the ADR itself
  authorizes this procedural edit), keeping the index cell in sync.

## Status updates (then re-run check_docs.py)

- After repo merge: ADR-0117 body `- **Status:**` →
  `Partially implemented (server, bindings, chart and tests merged; live Confluence Cloud verification pending)`;
  `docs/adr/README.md` ADR-0117 row → `Partially implemented`; tracker row →
  `Operator pending`; this file's State line.
- After operator steps: ADR-0117 → `Implemented - see \`components/mcp-servers/confluence/\`.`;
  index row → `Implemented`; tracker row → `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- ACL synchronization from Confluence (WP-25 / ADR-0110).
- `knowledge.project` chain extension (after WP-28/WP-31 / ADR-0209).
- Jira/Google/Salesforce servers (templated from this one during Phase 3).
