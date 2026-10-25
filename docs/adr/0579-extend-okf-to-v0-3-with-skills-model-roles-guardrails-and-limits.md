# ADR-0579: Extend OKF to v0.3 with skills, model roles, guardrails and limits

- **Status:** Accepted
- **Target:** v0.12
- **Date:** 2026-10-22
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0005](0005-use-okf-v0-2-as-the-declarative-agent-definition-contract.md), [ADR-0038](0038-use-standards-compliant-okf-v0-2-markdown-bundles.md), [ADR-0513](0513-give-okf-rag-tools-and-policies-directories-a-real-schema.md)
- **Related:** [ADR-0215](0215-carry-conversation-history-into-agent-prompts-with-budgeted-compaction.md), [ADR-0511](0511-define-okf-quota-policy-enforced-via-kuadrant.md), [ADR-0565](0565-derive-data-classification-from-okf-and-only-allow-raising-it.md), [ADR-0567](0567-move-trustyai-guardrails-into-the-ai-gateway.md), [ADR-0576](0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md), [ADR-0577](0577-publish-okf-as-per-agent-artifacts-plus-a-corp-index-artifact.md), [ADR-0581](0581-derive-stack-configuration-from-the-admitted-corp-bundle.md)

## Context

An OKF v0.2 bundle (`platform/okf/schema/zuno-okf-*-v0.2.schema.json`)
expresses an agent's tasks, prompts, MCP tools (`zuno.allowed_tools`), RAG
domains (`zuno.allowed_knowledge`, `zuno.rag.top_k`), memory
(`zuno.memory.history`, ADR-0215), entitlement (`zuno.access.groups`) and a
classification ceiling (`zuno.model.preferred_classification`). Several
things an agent owner reasonably wants to declare are not expressible, or
only indirectly:

- **Skills.** No notion exists. Reusable instructions shared by several
  tasks are copied between prompt files.
- **Models.** By design no model name appears in a bundle. The model chain
  comes from `policies/model-routing/model-routing-policy.yaml` keyed by
  (agent, task) and the catalog `platform/ai-gateway/provider-routing.yaml`,
  whose providers carry a `role` (`default`, `reasoning`, `quality`, `code`,
  `specialized`, `general-external`, `reasoning-external`). The agent owner
  edits a platform file to change a preference.
- **Guardrails.** Nothing in OKF. ADR-0567 evaluates guardrails in the
  ai-gateway, observe or block per classification, configured platform-side.
- **Limits and quotas.** `zuno.max_tokens` and `zuno.quota_class` exist per
  task; no task sets `quota_class`; there is no agent-level limit and no
  concurrency bound.

ADR-0576 moves the corp policies next to the bundles, so these declarations
can now live where agent owners work, provided they stay bounded by the
corp layer.

## Decision

**1. OKF v0.3 adds a `skill` document type.** `agents/<name>/skills/<skill>.md`,
frontmatter `type: skill`, `zuno.name`, `zuno.allowed_tools` (a subset the
skill needs), `zuno.allowed_knowledge` (likewise), body = reusable
instructions. A task lists `zuno.skills: [<skill>, ...]`; a skill's tools and
domains must be within the referencing task's own. The consumer appends the
skill bodies to the task's system prompt in the declared order. Corp-level
skills shared by every agent live in `skills/` at the repository root and
are referenced as `corp/<skill>`.

**2. `zuno.models` declares preferences by role, never by name.** On the
agent and optionally per task: `zuno.models.preferred: [<role>, ...]`
(ordered), `zuno.models.forbidden: [<role>, ...]`. Roles are those of the
platform contract (ADR-0576 clause 4). The ai-gateway keeps the final
choice: a preference is honoured only among providers eligible for the
effective classification (ADR-0021, ADR-0565); `model-routing-policy.yaml`
entries for an agent become generated from these declarations (ADR-0581).

**3. `zuno.guardrails` selects, per agent, how detections act.**
`zuno.guardrails.mode: observe | block` and an optional
`zuno.guardrails.categories` subset. A new machine-readable corp policy,
`policies/guardrails/guardrails-policy.yaml`, states per classification the
minimum mode (for example C3: `block`). An agent can only make it stricter.
Detection patterns stay in `zuno-demo` (`gitops/charts/trustyai-config`),
because they are platform configuration, not agent definition.

**4. `zuno.limits` groups the per-agent bounds.** On the agent, with task
override: `max_tokens` (moved from the task-only field, which remains valid
as an alias), `max_concurrent_requests`, `quota_class` (one of the classes
in `policies/quotas/quota-policy.yaml`) and `memory.history` (moved from
`zuno.memory`, alias kept).

**5. A bundle may only narrow the corp policies.** Validation (in
`zuno-demo-agents` CI and again at admission, ADR-0580) refuses any
declaration that widens: a tool or knowledge domain absent from the corp
policy for the agent's groups; a model role absent from the contract or not
eligible for the agent's classification; a guardrail mode weaker than the
corp minimum; a quota class or limit above what the corp policy allows. The
error names the clause of the corp policy that is exceeded.

**6. v0.2 stays readable for one release band.** A bundle declares
`okf_version: v0.3` to use these fields; v0.2 bundles validate and load
unchanged until the end of v0.12, after which v0.2 is refused. The schemas
live in `zuno-demo-agents` (`schema/zuno-okf-*-v0.3.schema.json`); every
consumer of the content (mcp-gateway `app/agent_declarations.py`, mlops,
`unifai-operator` `internal/okf/`, the stack generator of ADR-0581) reads
both versions during the window.

## Consequences

Agent owners express all of their intent in the bundle, and the platform
keeps the last word through the corp policies and the contract. The model
routing policy stops being a hand-edited platform file per agent.

Every consumer must implement v0.3 before any bundle uses it; WP-163 orders
consumers first, bundle migration last.

## Security considerations

Clause 5 is the security property: adding a field must never become a way
to widen access. The narrowing check runs twice, in the source repository
and at admission, so a compromised or misconfigured CI on one side cannot
admit a widening alone.

Skills are prompt text. A corp skill is appended to every referencing task's
system prompt, so it is reviewed with the same CODEOWNERS rule as
`policies/`.

## Operational considerations

No step of this decision touches a cluster. The schema change is a release
of `zuno-demo-agents`; its consumers ship before it is used.

## Amendment (2026-10-24) - optional delegation fields

Two optional fields are added to OKF v0.3, absent by default (which means no
delegation): `zuno.delegation.targets`, a list of `{agent, task}` the agent may
delegate to ([ADR-0401](0401-introduce-agent-delegation-limited-to-targets-an-agent-declares.md)),
and `zuno.limits.delegation.max_depth`, at most the corp ceiling
`max_delegation_depth` ([ADR-0406](0406-limit-agent-delegation-by-depth-cycle-and-budget.md)).
The corp limits policy also gains `delegation.allow_write` (default `false`).
No new `okf_version`: readers that ignore unknown optional fields are unaffected, and
the operator and schema are updated to accept them.

## Amendment (2026-10-25) - roles may reorder, not only narrow

Clause 5 says a bundle may only narrow the corp policies. For model ORDER the user decided otherwise on
2026-10-25: the `zuno.models.preferred` roles of a task, or else of the agent, reorder the candidates of the
corp routing entry for that task. Preferred roles come first, in role order; the other candidates follow
in corp order.

The narrowing rule still holds for everything else. An agent cannot add a model to the corp entry, loosen
`strict`, change `local_only_for`, or reach a model its classification does not allow. `forbidden` roles
still only exclude. How the generated routing file applies this is in the 2026-10-25 amendment of
[ADR-0581](0581-derive-stack-configuration-from-the-admitted-corp-bundle.md).
