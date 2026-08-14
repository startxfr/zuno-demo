# WP-01: Logical tool IDs and the backend-binding registry

- **State:** Repo work in review (2026-08-14 — all repo changes and status updates in the working tree; State flips to Done on merge)
- **ADRs:** ADR-0116 (To be implemented -> Implemented)
- **Depends on:** WP-00 (done)
- **Blocks:** WP-02, WP-26, WP-32
- **Estimated files touched:** ~8

> Execute this brief as a standalone task from the repository root. Read the
> referenced ADR sections before editing. If the repository state contradicts
> a step, stop and report instead of improvising.

## Goal

Replace the MCP Gateway's hard-coded tool-name routing with a platform-owned
backend-binding registry keyed by canonical logical capability IDs
(`<domain>.<resource>.<verb>`), failing closed on unknown capabilities. After
this WP, OKF bundles and policy reference logical IDs only, and changing a
physical MCP server requires only binding configuration.

## ADR references

Primary: [docs/adr/0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md](../../adr/0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md)

Acceptance criteria (verbatim from the ADR):

> - Agent/task OKF contains no MCP Service DNS names or URLs.
> - Changing the physical server for a logical capability requires only binding/deployment configuration, not agent/runtime behavior changes.
> - MCP Gateway no longer requires hard-coded per-tool routing sets in `downstream.py`.
> - Unknown logical capability or missing binding returns a deterministic denial/error without contacting an arbitrary backend.

Operational (verbatim): "Traces must record both the logical capability and
resolved backend binding. Health checks validate that every enabled policy
capability has exactly one valid active binding for the environment."

Migration (verbatim): "existing names such as `search_confluence`,
`list_drive_files`, `read_gmail` and `get_customer` may be maintained as
explicit aliases, but new agent contracts use canonical logical IDs."

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- `test -f components/mcp-gateway/app/downstream.py`
- `test -f policies/tools/tool-policy.yaml`
- Read fully before editing: `components/mcp-gateway/app/downstream.py`,
  `components/mcp-gateway/app/policy.py`, `components/mcp-gateway/app/main.py`,
  `policies/tools/tool-policy.yaml`,
  `components/mcp-gateway/tests/test_downstream_sales_db.py`.

## Repo changes (step by step)

1. **Create `platform/bindings/tools/tool-bindings.yaml`** — the backend-binding
   registry. One entry per logical capability currently served by the gateway
   (derive the current set from `downstream.py`'s hard-coded routing and
   `policies/tools/tool-policy.yaml`). Schema per entry:
   `capability` (canonical `<domain>.<resource>.<verb>` ID), `backend`
   (named MCP server / in-process handler), `transport`, `endpoint`
   (environment-resolved reference, e.g. env var or Service name — never a
   secret), `provider_tool` (the backend's native tool name), and optional
   `aliases:` list carrying the legacy names (`search_confluence`,
   `list_drive_files`, `read_gmail`, `get_customer`, …) found in
   `downstream.py` today. Add a README.md in `platform/bindings/tools/`
   stating: bindings are platform-controlled configuration, never supplied by
   an agent or caller (ADR-0116 Security considerations).
2. **Create `components/mcp-gateway/app/bindings.py`** — loader + resolver.
   Functions: `load_bindings(path)` (validate schema, reject duplicate
   capability IDs, reject a capability with zero or multiple active bindings),
   `resolve(capability_or_alias) -> Binding | None`. Resolution of an unknown
   name returns `None`; never fall through to a default backend.
3. **Refactor `components/mcp-gateway/app/downstream.py`** to route through
   `bindings.resolve()` instead of hard-coded tool-name sets. Keep the
   existing handler modules (`app/handlers/*.py`) as the in-process backends
   the bindings point at for now — this WP changes routing, not handler
   behavior. Authorization (`policy.evaluate()`) must still run **before**
   binding resolution/invocation, exactly as today.
4. **Fail closed:** an unknown capability or a capability without a binding
   returns the gateway's existing deterministic denial/error shape (mirror
   how an unauthorized tool call is refused today; do not invent a new error
   format).
5. **Traces:** where the gateway currently records the tool name (see
   `app/telemetry.py`), also record the logical capability and the resolved
   backend binding name.
6. **Startup/health validation:** at gateway startup, validate every
   capability listed in `policies/tools/tool-policy.yaml` resolves to exactly
   one active binding; log and fail loudly otherwise (mirror the existing
   startup pattern in `app/main.py`).
7. **Tests** in `components/mcp-gateway/tests/` (mirror
   `test_downstream_sales_db.py` style):
   - alias and canonical ID resolve to the same binding;
   - unknown capability → deterministic denial, no backend contacted;
   - capability missing a binding → deterministic denial;
   - startup validation fails when a policy capability has no binding.
8. **Policy file:** add the canonical capability IDs to
   `policies/tools/tool-policy.yaml` entries alongside (not replacing) the
   legacy names, following the file's own commented conventions. Do not
   remove legacy names in this WP.

## What NOT to touch

- Decision text of any existing ADR (immutable; direction changes need a superseding ADR).
- The uncommitted ADR-0344 change set if still present in `git status`
  (`Makefile`, `ansible/playbooks/day0_*.yml`, `ansible/roles/openshift_ai/**`,
  `ansible/tasks/*gitops_app*.yml`, `ansible/tasks/*blocked_finding*.yml`).
- `gitops/apps/*` `targetRevision` values and chart `image.tag` values (owned by WP-04).
- OKF bundles under `agents/` (they migrate to canonical IDs in later WPs).
- Handler business logic in `components/mcp-gateway/app/handlers/*.py`.

## Acceptance checks (run from repo root; all must pass)

- `python3 -m py_compile components/mcp-gateway/app/bindings.py components/mcp-gateway/app/downstream.py`
- `python3 -m pytest components/mcp-gateway/tests/ -q` (all pass)
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`
- `grep -n "confluence.page.search" platform/bindings/tools/tool-bindings.yaml` (registry exists and carries canonical IDs)
- No hard-coded per-tool routing set remains in `downstream.py`: manually
  confirm routing goes through `bindings.resolve()`.

## Operator / human follow-up

None. This WP is fully provable from the repository; ADR-0116 moves straight
to Implemented once the checks pass and the change is merged.

## Status updates (after merge; then re-run check_docs.py)

1. `docs/adr/0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md`:
   `- **Status:**` → `Implemented - see \`platform/bindings/tools/\`, \`components/mcp-gateway/app/bindings.py\`.`
2. `docs/adr/README.md`: ADR-0116 row status cell → `Implemented`.
3. `docs/roadmap/v0.1-v0.3-implementation-roadmap.md`: WP-01 tracker row → `Done`.
4. This file: `- **State:**` → `Done`.
5. `MEMORY.md`: one dated bullet in the MCP/tools section describing the
   binding registry as implemented state.

## Out of scope / deferred

- The real Confluence MCP server consuming the registry (WP-02).
- `auth_mode` field per binding (WP-26 / ADR-0208).
- Migrating OKF bundles to canonical IDs (WP-31/WP-33 agent slices).
