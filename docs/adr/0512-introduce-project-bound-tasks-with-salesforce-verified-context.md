# ADR-0512: Introduce project-bound tasks with Salesforce-verified context

- **Status:** Partially implemented (schema, prompts, runtime binding and scoping merged; live Salesforce verification pending)
- **Target:** v0.3 (retargeted from OKF v0.1 on 2026-08-24 — WP-55 has a hard `Depends on: WP-54`, which is retargeted to v0.3 alongside ADR-0511; moves with it rather than sitting blocked inside the OKF v0.1 milestone)
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team

## Context

Some agent work only makes sense inside a client engagement: Finage's
`identify-business-ready-to-invoice` and `monthly-invoice-report` tasks
reason about specific business, and any task consuming ADR-0209's
`knowledge.project` domain reads memory keyed by a mandatory
`project_id`. Yet no task can *require* a project today — a user can
start any conversation with no engagement context, and `project_id`
enters the system only as an optional, unverified value (ADR-0212's
`conversations.project_id` column is nullable and client-supplied). The
platform has the verification surface already: Salesforce is the system
of record for engagements, reachable through the MCP Gateway's governed
capabilities (`salesforce.opportunity.read`, the ADR-0206 current-Salesforce
knowledge separation) with the full ADR-0036 intersection applied. And
ADR-0511 gives projects their own quota — which is only meaningful if
project identity is verified, not asserted.

## Decision

1. **A task can be marked project-only in its frontmatter:**
   `zuno.project_required: true` (schema addition in
   `platform/okf/schema/zuno-okf-task-v0.2.schema.json`, default
   `false`). The ADR-0503 matrix surfaces the mark to operators, and
   ADR-0515's conversation-creation flow surfaces it to the user before a
   `project_required` task starts; the ADR-0504 contract tests validate it
   (a `project_required` task must declare at least one project-scopable
   resource).

2. **The prompt collects the project before any action.** For a
   `project_required` task, the task's prompt template must open by
   requesting the project name or Salesforce id as **mandatory session
   context** — the graph takes no tool call, no retrieval and no model
   action on the user's request until the binding exists. Prompt-side
   collection is UX; enforcement is server-side (clause 3): Agent
   Runtime refuses to execute a `project_required` task without a
   verified binding, fail-closed.

3. **The binding is verified against Salesforce before the conversation
   starts.** On task start with a candidate project, Agent Runtime
   resolves and validates it through the MCP Gateway
   (`salesforce.opportunity.read`) under the caller's own identity
   (ADR-0013/ADR-0032) — so the check proves both that the project
   exists and that *this user* may read it; the gateway's intersection
   does the authorization work it already does. Success yields a
   verified `project_id` recorded on the conversation row (ADR-0212's
   `project_id` column stops being client-asserted for these tasks);
   failure, or Salesforce being unreachable, blocks the conversation
   with an explicit error — a `project_required` task never proceeds
   unverified. The binding is per-conversation and re-verified on
   resume after a policy-defined validity window.

4. **A verified binding activates the project dimension everywhere it
   exists:** the project's ADR-0511 quota (drawn down first, before user
   and group, per that ADR's precedence), `knowledge.project` retrieval
   scoped to the bound `project_id` (ADR-0209's mandatory-key contract,
   now fed a verified value), and conversation metadata for listing and
   sharing (ADR-0212/ADR-0213). Tasks without the mark are unchanged —
   they may still receive an optional project link as today.

## Consequences

Project-only work gets an enforceable boundary instead of a convention:
the finance tasks and any future engagement-scoped task declare the
requirement in OKF, and the platform guarantees a verified engagement
context before a single action runs. Agent Runtime gains a pre-execution
verification step and a small binding cache; the MCP Gateway gains
nothing new — verification rides existing governed capabilities. WP-55
implements this ADR after WP-54 lands the quota substrate.

## Security considerations

Verification under the caller's identity is the point: a user who cannot
read the opportunity in Salesforce cannot bind to it, so project quota
and project memory can never be reached by name-guessing. Fail-closed is
absolute for `project_required` tasks — Salesforce downtime pauses
project-bound work rather than degrading it to unverified. The binding
is stored as an id plus verification timestamp, never Salesforce record
content; transcripts and the conversations table gain no new business
data. Re-verification on resume bounds the window in which revoked
Salesforce access lingers on an open conversation.

## Operational considerations

The verification call is one governed MCP read at conversation start —
latency lands once per conversation, not per turn. Verification
failures are observable per cause (unknown project, no access,
Salesforce unreachable) so a Salesforce outage is distinguishable from
an authorization denial. The validity window and cache behavior are
declared beside the quota classes in `policies/quotas/quota-policy.yaml`
rather than hardcoded.

## Acceptance criteria

- A `project_required` Finage task refuses to act until a project is
  provided, verifies it via `salesforce.opportunity.read` under the
  caller's identity, and records the verified `project_id` on the
  conversation.
- A user without Salesforce access to the named project is denied the
  binding; with Salesforce unreachable the task blocks with an explicit
  error — both fail-closed, both covered by security-negative tests.
- A bound conversation draws down project quota first (ADR-0511) and
  scopes `knowledge.project` retrieval to the bound id.
- Unmarked tasks behave exactly as before.

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Migration/evolution and Review evidence.

## Implementation note (2026-08-21) — WP-55 repo work merged; a real policy-grant gap found and left for the operator

All four Decision clauses landed: the `zuno.project_required` schema mark
(`platform/okf/schema/zuno-okf-task-v0.2.schema.json`), Finage's
`identify-business-ready-to-invoice`/`monthly-invoice-report` tasks marked
and given dedicated prompts that open by requesting the project;
`components/agent-runtime/app/project_binding.py` (new) verifies a
candidate via `salesforce.opportunity.read` under the caller's own
identity, fail-closed with three distinguishable causes (unknown project
/ no access / unreachable → 404/403/503), never routed through
`tool_call_node` so it never reaches the model's own context (preserves
the Comage/Finage Salesforce-content boundary this ADR's own Security
considerations draw); a verified binding is cached on
`conversations.project_id`/new `project_id_verified_at`
(`app/conversations.py`) and re-verified past
`policies/quotas/quota-policy.yaml`'s `project_binding.validity_window`;
`X-Zuno-Project-Id` now reaches ai-gateway's quota ledger, gated strictly
on the task's own `project_required` mark (never merely on `project_id`
being truthy — closes an abuse channel an ungated implementation would
have opened); `knowledge.project` retrieval scoping needed no new code,
only a verified value fed into machinery already fail-closed on it.

**A real, load-bearing gap found live in the repo, not fixed here per
this WP's own "what NOT to touch"**: `salesforce.opportunity.read`
(`policies/tools/tool-policy.yaml`) is granted only to
`allowed_groups: [sales, board]`. Finage's real business-role group is
`finance` (`platform/identity/README.md`), which is not in that list —
the `salesforce` MCP server's own module docstring frames the capability
as "Comage's live Salesforce integration" (ADR-0326/WP-33). As merged, no
real Finage user can successfully bind a project today — every attempt
correctly fails closed with `no_access` — until a separate, reviewed
`tool-policy.yaml` grant change adds the right group. This is a
standalone operator/policy decision, not a repo defect.

MCP Gateway: zero changes, as this ADR's Decision text requires —
verification rides the existing `salesforce.opportunity.read`
authorization intersection unchanged. Live Salesforce verification
(the operator follow-up below) remains blocked on the standing WP-22/
WP-33 sandbox credential gap, same as WP-23/WP-065's own live pass.

## Related ADRs

- [ADR-0013](0013-propagate-end-user-identity-through-agent-calls.md)
- [ADR-0032](0032-propagate-trusted-identity-end-to-end.md)
- [ADR-0036](0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md)
- [ADR-0206](0206-separate-current-salesforce-knowledge-from-legacy-sxa.md)
- [ADR-0209](0209-introduce-project-scoped-agent-memory.md)
- [ADR-0212](0212-introduce-persistent-navigable-chat-conversations.md)
- [ADR-0503](0503-make-each-okf-bundle-state-its-complete-authorization-contract.md)
- [ADR-0504](0504-define-the-agent-tests-directory-structure-and-promotion-gate.md)
- [ADR-0511](0511-define-okf-quota-policy-enforced-via-kuadrant.md)
- [ADR-0515](0515-per-conversation-tabs-one-browser-tab-per-agent.md)
