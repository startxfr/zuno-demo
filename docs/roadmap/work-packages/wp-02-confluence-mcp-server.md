# WP-02: Real Confluence MCP server

- **State:** Done (2026-08-18 — the Atlassian product-access grant landed (the 2026-08-17 `403` no longer reproduces; `/wiki/api/v2/spaces` returns 200 with 42 real spaces) and the live e2e chain ran end to end: (1) indexed `knowledge.tech` read via `rag-service /v1/search` returned real indexed chunks; (2) `search_confluence` (alias → `confluence.page.search`) invoked through `mcp-gateway /v1/tools/.../invoke` as `consultant-01` under `X-Zuno-Agent: tekos`/`find-relevant-docs` → 200 with real `SXS` space results; (3) `confluence.page.read` through the gateway as `arkos`/`draft-architecture-testimonial` → 200 (`S0R81-UPMHT`, v1); (4) deny path: `confluence.page.create` through the gateway → 403 `agent 'tekos' does not declare tool 'confluence.page.create' in any task (ADR-0011 agent_declaration)`; (5) `create_page`+`update_page` verified against the real Confluence REST API via the streamable-HTTP MCP endpoint with the `X-Zuno-Gateway-Token` service identity, confined to the technical identity's own personal space (page `1033142273` created v1 → updated v2 → deleted, zero footprint in shared spaces). ADR-0043's status-line follow-up executed in the same change. Pre-existing `zuno-mcp-confluence-d1` `OutOfSync`/`Healthy` sync-wave collision on the shared `mcp-gateway-workload-token` ExternalSecret remains out of scope, as recorded 2026-08-17.)
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
capabilities via WP-01's binding registry, replacing the demo-mode
handler. Repo work lands everything except live Confluence Cloud
verification (an operator step).

## ADR references

Primary: [docs/adr/0117-implement-confluence-as-the-first-real-external-mcp-integration.md](../../adr/0117-implement-confluence-as-the-first-real-external-mcp-integration.md)

Acceptance criteria: the four `confluence.page.*` capabilities execute against real Confluence Cloud through the gateway, not the demo handler; a task chains a `knowledge.tech` read with a live Confluence read/write (`knowledge.project` later, per ADR-0209); Agent Runtime/OKF carry no Confluence URL, credential, or vendor tool name — only the four logical IDs; an end-to-end test covers the full chain, and the demo handler is removed once it passes. ADR-0043's status line updates once criteria are met (procedural — see Post-operator repo follow-up below).

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
