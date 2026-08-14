# WP-26: Per-binding authentication modes and audit

- **State:** Not started
- **ADRs:** ADR-0208 (To be implemented -> Implemented)
- **Depends on:** WP-01 (merged)
- **Blocks:** WP-31, WP-32, WP-33
- **Estimated files touched:** ~6

> Execute this brief as a standalone task from the repository root.

## Goal

Give every physical tool binding an explicit, non-inferred authentication
mode (`delegated-user` | `service-identity` | `provider-delegated`),
enforced by the MCP Gateway, with Google Workspace capabilities running
delegated-user (extending ADR-0014's existing flow) and audit records
carrying subject + capability + binding + mode — never token material.

## ADR references

Primary: [docs/adr/0208-standardize-enterprise-tool-authentication-and-delegation.md](../../adr/0208-standardize-enterprise-tool-authentication-and-delegation.md)

Acceptance criteria: Drive/Gmail/Calendar/Meet calls execute with the user's delegated Google identity; removing a user's Google permission prevents access even when Zuno still allows the logical capability; backend bindings declare authentication mode explicitly; no OKF document or RAG chunk contains downstream credentials/tokens.

Body constraints: mode is "explicit config, never inferred from the tool
name"; where service identity is unavoidable, server-side filters apply from
the validated initiating user/role; provider tokens stay server-side, never
in OKF, prompts, browser storage or RAG content; delegated tokens stored per
ADR-0042/secret management.

## Preconditions (verify before starting)

- WP-01 merged: `test -f platform/bindings/tools/tool-bindings.yaml`.
- `python3 platform/docs/check_docs.py` exits 0.
- Read: `components/mcp-gateway/app/bindings.py` (WP-01's loader — extend
  it), `components/mcp-gateway/app/handlers/{drive,gmail}.py` and
  `components/mcp-servers/google-workspace/` (how ADR-0014 delegated OAuth
  flows today), `components/mcp-gateway/app/auth.py` + `telemetry.py`
  (where audit fields are emitted).

## Repo changes (step by step)

1. **Schema:** add a required `auth_mode` field
   (`delegated-user | service-identity | provider-delegated`) to every entry
   in `platform/bindings/tools/tool-bindings.yaml`; loader validation in
   `bindings.py` rejects a missing/unknown mode (fail closed — an entry
   without a mode never loads).
2. **Assignments:** `drive.*`, `gmail.*`, `calendar.*`, `meet.*` →
   `delegated-user`; `confluence.page.*` → `service-identity` (matches
   ADR-0117); `salesforce.*`, `workday.*`, `jira.*` get their mode when
   their real bindings land (leave present entries accurate to today's
   backends).
3. **Enforcement:** in the gateway invocation path, the credential flow used
   must match the declared mode: `delegated-user` requires the caller's
   delegated token (reuse the ADR-0014 flow — no delegated token present →
   deterministic denial, not service-identity fallback); `service-identity`
   requires policy evaluation to have passed for the specific subject before
   the shared credential is used.
4. **Audit:** extend the gateway's audit/trace emission with
   `auth_mode` + resolved binding alongside the existing subject/capability
   fields; add a test asserting no token material appears in logs/traces.
5. **Tests:** mode-mismatch fails closed; delegated-user without token →
   denial; revoked-Google-permission behavior asserted at the mock level
   (real revocation is the operator check); binding without `auth_mode`
   fails to load.

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set.
- The Google OAuth flow itself (ADR-0014 — reuse, don't rework).
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m pytest components/mcp-gateway/tests/ -q`
- `grep -c "auth_mode" platform/bindings/tools/tool-bindings.yaml` equals the number of binding entries
- `! grep -rn "refresh_token\|api_token" agents/ knowledge/` (no credentials in contracts)
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up

Optional live confirmation: revoke a test user's Google Drive permission and
verify the call fails despite Zuno authorization. The decision itself is
repo-provable (the delegated flow already exists per ADR-0014), so ADR-0208
moves to Implemented on merge; record the live check when performed.

## Status updates (then re-run check_docs.py)

- After merge: ADR-0208 →
  `Implemented - see \`platform/bindings/tools/tool-bindings.yaml\`, \`components/mcp-gateway/app/bindings.py\`.`;
  index row `Implemented`; tracker → `Done`; this file's State; MEMORY.md
  dated bullet.

## Out of scope / deferred

- `provider-delegated` (on-behalf-of) concrete implementation — mode exists
  in the schema; first real use arrives with a provider that supports it.
- Workday/Jira/Salesforce real bindings (Phase 3 agent slices).
