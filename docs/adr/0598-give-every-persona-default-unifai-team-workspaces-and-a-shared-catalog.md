# ADR-0598: Give every persona default UnifAI team workspaces and a shared catalog

- **Status:** Proposed
- **Target:** v0.13
- **Date:** 2026-11-04
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0583](0583-require-group-visibility-and-object-level-authorisation-before-per-agent-entries.md) (OIDC group members, extended), [ADR-0349](0349-restructure-demo-personas-cluster-access-groups-and-new-agents.md) (the business groups), [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md) (agent groups apart from business roles), [ADR-0597](0597-declare-unifai-built-in-resources-through-the-operator.md) (the built-ins), [ADR-0562](0562-authenticate-unifai-against-the-zuno-keycloak-realm.md)

## Context

consultant-01 logged into UnifAI on 2026-11-04 and could do nothing. The sidebar said "No teams yet", and the inventory,
workflow, chat and RAG pages were all empty. Two causes:

- **The wrong stack.** The screenshots were of `unifai-devel`, the operator sandbox. Its examples are owned by `admin`, and
  it reads no Keycloak groups.
- **Agent teams only on `zuno-unifai`.** The stack with the demo has only the teams that the agent bundles emit
  (`agent-tekos`, `agent-arkos`, `agent-comage`). The rest of the inventory belongs to ai-ops-01.

So a persona only sees the workspaces of the agents it is entitled to, and has no workspace for its business role. The only
templates in the catalog asked for a Gemini API key.

## Decision

1. **Two kinds of teams, side by side.**
   - The agent teams `agent-<bundle>` stay as they are. Each holds that agent's workflows.
   - Each business group of the zuno realm also gets one team, created through the UnifaiTeam resource with
     `{type: group}` members: `consultant`, `sales`, `adv`, `finance`, `board`, `recrut` and `cdp`.
   - An `ops` team gathers `ocp-ai-ops` and `ocp-paas-ops`.
   - Membership follows the token's groups (oidc-claims, ADR-0583). Keycloak stays the only place where people are
     assigned.
   - The list is declared per cluster (`zuno_unifai_values.teams`) and owned by the platform admin, so only an UnifAI admin
     can change these teams in the UI.
2. **A catalog without secrets.** The public templates `zuno-chat`, `zuno-tools-agent` and `zuno-draft-review` embed the
   gateway LLM (and, for tools, the MCP provider), both with the user's token forwarded. "Configure & Generate" gives a
   working workflow at once.
3. **Shared inventory.** `zuno-gateway` and `mcp-gateway` become public built-ins (ADR-0597). The `knowledge-*` retrievers
   stay in their agent team: UnifAI has no built-in retrievers, and the RAG ACLs apply per user anyway.
4. **Example workflows.** Each business team that has personas gets example workflows on the built-in gateway: linear,
   branches, orchestrated and RAG.
5. **Personal starters.** A short list of demo personas (consultant-01, sale-01, ai-ops-01) gets starter workflows in their
   personal workspace. These are declarative `UnifaiWorkflow` objects with `owner: <username>`, recreated if deleted.
6. **`unifai-devel` stays a sandbox.** Its examples move onto the gateway LLM and the zuno templates, so they run without an
   external key.

## Consequences

- A new business group needs a Keycloak change, which the create-only realm import cannot do. It also needs a line in the
  cluster's `teams`.
- Team names are global in UnifAI identity. A team of the same name that a user created first is not taken over (UnifaiTeam
  semantics), and the chart's object reports it.
- Points 3 to 5 depend on the operator release that carries ADR-0597. Points 1 and 2 do not.
