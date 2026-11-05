# ADR-0597: Declare UnifAI built-in resources through the operator

- **Status:** Proposed
- **Target:** v0.13
- **Date:** 2026-11-04
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0560](0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md) (the gateway LLM), [ADR-0563](0563-forward-caller-identity-and-zuno-context-headers-from-unifai.md) (forwarded user token), [ADR-0569](0569-close-unifai-parity-gaps-generically.md) (generic fixes go to the fork), [ADR-0598](0598-give-every-persona-default-unifai-team-workspaces-and-a-shared-catalog.md) (the default workspaces that use them)

## Context

On 2026-11-04 consultant-01 opened UnifAI and found an empty inventory. On `zuno-unifai`, the platform's shared LLM
(`zuno-gateway`, the ai-gateway) and its MCP provider (`mcp-gateway`) are owned by `ai-ops-01` and stored in that user's
personal workspace. A UnifAI resource is visible only to its owner or to the members of its team workspace. Every other
persona therefore sees neither of them and cannot reference them in their own workflows.

UnifAI already has a native answer: **built-in resources**. An admin creates them, a descriptor marks them public, and
every user then sees them in the inventory's "Built-in" tab. Only admins can change them, and UnifAI promotes the
resources they reference together with them. The operator only spoke the custom-resource API, so it could not declare
them.

## Decision

1. **The field.** Six resource kinds gain an optional `spec.builtin: bool`: UnifaiLLM, Provider, Tool, Condition, Sandbox
   and Agent.
   - With `builtin: true`, the operator saves the resource as its owner, exactly as before.
   - It then calls `PATCH /api/resources/builtin.toggle` with `availableToAll: true`.
   - It calls it again only when the pushed spec changes. The hash includes the flag only for built-ins, so objects that
     don't use it are not pushed again.
2. **UnifaiRetriever has no `builtin`.** UnifAI refuses built-in retrievers (`builtin_disabled_categories`).
3. **The owner must be an UnifAI admin.** A non-admin owner gets a permanent `Error` that says so.
4. **Promotion happens in place.** Turning the flag on for an existing object promotes its resource and keeps its rid, so no
   orphan copy is left.
5. **The flag cannot be turned off.** A CRD transition rule refuses it, because UnifAI has no way to turn a built-in back
   into a personal resource. To withdraw a built-in, delete the object.
6. **Built-ins have no team workspace.** `builtin` is exclusive with `teamId` and `teamRef`. A CEL rule enforces this, and
   the static rule table (`internal/validate`) does the same check.
7. **The change belongs in the fork.** It goes into the operator in the fork (`startx-unifai`, fork/unifai-operator), per
   ADR-0569. It ships in the fork's release lifecycle: alpha channel, catalog pinned by digest.

## Consequences

- One copy of the gateway LLM and MCP provider serves every user and every team workspace. Team workflows and persona
  starters can then reference `zuno-gateway` (ADR-0598).
- A public built-in appears in every user's resource list. Another admin's built-in with the same name is therefore a name
  collision, reported as "not managed" like any other.
- Changing a built-in's config is still an admin action. The operator's owner must stay in `adminUsers`.
