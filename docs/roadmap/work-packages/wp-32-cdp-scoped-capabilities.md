# WP-32: `cdp` role and scoped capabilities

- **State:** Not started
- **ADRs:** ADR-0340 (To be implemented -> Implemented)
- **Depends on:** WP-01 (merged); WP-20 (knowledge policy exists for the intent matrix)
- **Blocks:** WP-33 (Comage roles), board-role correctness for all slices
- **Estimated files touched:** ~7

> Execute this brief as a standalone task from the repository root.

## Goal

Extend business-role vocabulary with `cdp` (project manager), encode the
read/write-scoped capability pattern (`workday.profile.self.read` /
`self.update` / `any.read`) in the policy files, publish the access-intent
matrix as derived documentation, and migrate ADR-0330's temporary
`/board`-as-architect grouping so `board` consistently means Direction.

## ADR references

Primary: [docs/adr/0340-extend-business-role-authorization-with-cdp-and-scoped-capabilities.md](../../adr/0340-extend-business-role-authorization-with-cdp-and-scoped-capabilities.md)

Acceptance criteria: Keycloak gets a `cdp` business role without changing
agent-entitlement semantics; self vs. any read/write scoping is enforced
(technical self-updates only, CDP gets self.read + any.read but no
any.update); a role cannot use a capability absent from the active
agent/task OKF declaration; no independent AI-profile store is required.

Body constraints: role mapping technical→`consultant`, project manager→new
`cdp`, sales→`sales`, ADV→`adv`, direction→`board`, finance→`finance`;
`architecture`/`build`/`run` are skill/data scopes, not business roles; the
access-intent table must be encoded in the policy files to take effect —
the matrix doc is derived output, never an authorization source;
`*.self.*`/`*.any.*` ownership checks are server-side from validated
identity claims, never prompt text.

## Preconditions (verify before starting)

- WP-01 merged (binding registry for the capability entries).
- `python3 platform/docs/check_docs.py` exits 0.
- Read: `gitops/charts/keycloak/files/realm-zuno.json` (roles/groups,
  including ADR-0330's `confluence-archi-*` groups under `/board`),
  `policies/tools/tool-policy.yaml`, `policies/knowledge/knowledge-policy.yaml`,
  ADR-0340's access-intent table in the ADR body (the source for step 4).

## Repo changes (step by step)

1. **Keycloak realm:** add the `cdp` business role/group in
   `realm-zuno.json` following the existing role structure; do not alter
   agent-entitlement (`agent_*`) semantics.
2. **Board migration:** move the ADR-0330 demo `confluence-archi-*` groups
   out of `/board` to the correct technical container (`/consultant` with an
   `architecture` skill scope, per the ADR's scope model) so `board` means
   Direction only. Update any policy references to those group paths
   (`grep -rn "board" policies/ gitops/charts/keycloak/`).
3. **Workday capabilities:** register `workday.profile.self.read`,
   `workday.profile.self.update`, `workday.profile.any.read` in
   `platform/bindings/tools/tool-bindings.yaml` (binding may point at a
   stub/planned backend with an explicit `status: no-backend` marker that
   fails closed at resolution — WP-01's loader already denies missing
   bindings) and in `policies/tools/tool-policy.yaml` with the role
   assignments from the ADR (technical: self read/write; cdp: self.read +
   any.read; `any.update` deliberately absent).
4. **Access-intent encoding:** encode the ADR's full intent table
   (consultant/tech, cdp, sales, adv, board, finance × knowledge domains ×
   tool families) into `policies/tools/tool-policy.yaml` and
   `policies/knowledge/knowledge-policy.yaml`.
5. **Derived matrix doc:** generate/write
   `docs/security/access-intent-matrix.md` stating explicitly it is derived
   from the policy files (list them) and is not an authorization source.
6. **Server-side scope checks:** in the MCP Gateway invocation path, enforce
   `*.self.*` subject matching from the validated JWT subject (never from
   prompt content); test both allow and deny.
7. **Tests:** one per acceptance bullet (mock Workday backend; the
   OKF-declaration bullet reuses the WP-20 intersection test pattern).

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set.
- Agent-entitlement group semantics (ADR-0040 boundary).
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m json.tool gitops/charts/keycloak/files/realm-zuno.json > /dev/null`
- `python3 -m pytest components/mcp-gateway/tests/ -q`
- `grep -n "cdp" gitops/charts/keycloak/files/realm-zuno.json`
- `! grep -rn "confluence-archi" policies/ | grep "/board"` (migration done)
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up (not executable by the model)

1. Operator: re-apply the realm (`make d0 install keycloak` or the realm
   re-apply path) and verify the `cdp` role + moved groups with a real
   login.

## Status updates (then re-run check_docs.py)

- After merge + realm re-apply: ADR-0340 →
  `Implemented - see \`gitops/charts/keycloak/files/realm-zuno.json\`, \`policies/\`.`;
  index row `Implemented`; tracker → `Done`; this file's State; MEMORY.md
  dated bullet. (If the operator step lags the merge, pass through
  `Partially implemented (policy and realm merged; realm re-apply pending)`.)

## Out of scope / deferred

- A real Workday MCP backend (capabilities fail closed until one exists).
- Per-agent role usage (WP-33+ slices consume the new roles).
