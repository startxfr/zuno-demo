# WP-55: Project-bound tasks (promotes ADR-0512)

- **State:** Not started
- **ADRs:** ADR-0512
- **Depends on:** WP-54 (quota substrate; the binding validity window
  lives in quota-policy.yaml); WP-061 Part A recommended first
  (prompt-example schema chain). Note: WP-47 (abandoned, superseded by
  WP-061/ADR-0515) would have added a chat-contract `task` parameter to
  name which task demands the binding — WP-061 does not add one, so this
  brief must confirm at implementation time how a `project_required` task
  is identified at conversation start under ADR-0515's per-conversation
  model.
- **Estimated files touched:** ~14

> Execute this brief as a standalone task from the repository root.
> Tracked in [docs/roadmap/okf-roadmap.md](../okf-roadmap.md).

## Goal

`zuno.project_required: true` tasks demand a Salesforce-verified project
id as mandatory session context before any action: prompt collects it,
Agent Runtime verifies it via the MCP Gateway under the caller's own
identity, fail-closed; a verified binding activates project quota
precedence and scopes `knowledge.project` to the bound id.

## ADR references

ADR-0512 clauses 1–4; ADR-0511 clause 2 (precedence); ADR-0209
(`knowledge.project` mandatory `project_id`); ADR-0212
(`conversations.project_id` column).

## Preconditions (verify before starting)

- WP-54 merged. Verify `salesforce.opportunity.read` exists in
  `policies/tools/tool-policy.yaml` and which MCP server binds it
  (`platform/bindings/`); real Salesforce credentials are a known
  operator gap (WP-22/WP-33) — repo work must be provable against the
  mcp-servers sales fixtures.
- Read: `components/agent-runtime/app/main.py` chat route +
  `registry.py`; `components/mcp-gateway/app/policy.py` (the
  intersection the verification call rides); ADR-0212's conversation
  schema if merged.
- mcp-gateway tests need a venv built from the component's own
  requirements.txt.

## Repo changes (step by step)

1. Schema: `zuno.project_required` (boolean, default false) on task
   frontmatter; validator + ADR-0504 structure rule (a
   `project_required` task declares ≥1 project-scopable resource);
   regenerate matrices (the mark renders per ADR-0503).
2. Mark Finage's `identify-business-ready-to-invoice` and
   `monthly-invoice-report` tasks `project_required: true`; extend
   their prompts to open by requesting the project (name or Salesforce
   id) as mandatory session context.
3. Agent Runtime: pre-execution binding step for `project_required`
   tasks — resolve/verify the candidate project through the MCP
   Gateway (`salesforce.opportunity.read`) under the caller's identity;
   on success record verified `project_id` (+ timestamp) on the
   conversation row (or in-graph state pre-0212); on failure or
   Salesforce unreachable, block with a cause-distinguished error
   (unknown project / no access / unreachable) — never proceed
   unverified; re-verify on resume past the validity window.
4. Wire the binding into: quota precedence (project drawn first, WP-54
   contract), `knowledge.project` retrieval scoping (bound id only),
   and the chat contract/BFF passthrough for supplying the candidate
   project (OpenAPI-first per ADR-0054).
5. Tests incl. security-negative: no-access user denied the binding;
   unreachable Salesforce blocks (fail-closed); unmarked tasks
   byte-identical behavior; bound conversation draws project quota
   first and retrieves only bound-id project memory.

## What NOT to touch

Standard list; plus: MCP Gateway authorization logic (verification
rides the existing intersection — zero gateway changes by design);
`policies/tools/tool-policy.yaml` grants (if Finage's groups lack the
Salesforce capability, stop and surface it — a policy change is its own
reviewed decision, not a drive-by).

## Acceptance checks (run from repo root; all must pass)

- Bundle validation + matrix `--check` green with the new mark.
- Runtime suite green including all security-negative cases above,
  against the sales fixtures.
- `check_docs.py` passes.

## Operator / human follow-up (not executable by the model)

With sandbox Salesforce credentials (the standing WP-22/WP-33 gap): one
live bind-verify-converse pass on a Finage project task; one live
denial for a user without access to the named opportunity.

## Status updates (then re-run check_docs.py)

On merge: ADR-0512 → `Partially implemented (schema, prompts, runtime
binding and scoping merged; live Salesforce verification pending)`;
after the live pass → `Implemented - see components/agent-runtime/ and
agents/finage/tasks/.` Index + tracker + MEMORY.md accordingly.

## Out of scope / deferred

- Project pickers/browse UX beyond prompt collection (ADR-0407
  territory). Multi-project conversations. Non-Salesforce project
  registries.
