# ADR-0581: Derive stack configuration from the admitted corp bundle

- **Status:** Accepted
- **Target:** v0.12
- **Date:** 2026-10-22
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md), [ADR-0511](0511-define-okf-quota-policy-enforced-via-kuadrant.md), [ADR-0530](0530-reconcile-keycloak-clients-instead-of-relying-on-a-create-only-realm-import.md), [ADR-0564](0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md), [ADR-0567](0567-move-trustyai-guardrails-into-the-ai-gateway.md), [ADR-0570](0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md), [ADR-0576](0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md), [ADR-0579](0579-extend-okf-to-v0-3-with-skills-model-roles-guardrails-and-limits.md), [ADR-0580](0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md)

## Context

What an agent may do is declared in its bundle, but most of the stack that
enforces it is configured by hand, and copies drift:

- **Keycloak.** The `agent_<name>` entitlement groups (ADR-0040) are typed
  into `gitops/charts/keycloak/files/realm-zuno.json`; the scaffolds'
  `keycloak-fragment.json` files are merged by hand. The realm import is
  create-only, and the ADR-0530 reconcile Job covers clients only.
- **MaaS.** `gitops/charts/models/values.yaml` lists subscription groups per
  model by hand (for example `/agent_tekos`).
- **Kuadrant.** `platform/okf/generate_quota_enforcement.py` turns
  `policies/quotas/quota-policy.yaml` into the `connectivity-link`
  RateLimitPolicies and `components/ai-gateway/app/quota_budgets.yaml`.
- **Per-agent chart values.** `gitops/charts/arkos/values.yaml` carries
  `knowledgeDomains`, `toolCapabilities` and `groups`, hand-copied as the
  "union of every agents/arkos/tasks/*.md".
- **UnifAI.** `okf.bundles[]` (digests, ceilings, entitlement) is filled by
  hand through `zuno_unifai_values` in `ansible/confidential.yml`.
- **Model routing.** `policies/model-routing/model-routing-policy.yaml` is
  edited per (agent, task).

With ADR-0580 one digest names the agents release. Everything above can be
computed from that release plus the platform's own files.

## Decision

**1. One generator, `platform/okf/generate_stack_config.py`, derives the
stack configuration from the admitted corp bundle.** Input: the artifacts
named by `platform/okf/agents.lock`, pulled and verified as admission does
(ADR-0580 clause 3), plus `zuno-demo`'s own catalog and bindings. Output:
generated files committed to git, each with a header naming the corp digest
it came from. It absorbs `generate_quota_enforcement.py`.

**2. What it generates.**

| Target | Generated file | From |
|---|---|---|
| Keycloak entitlement groups | `gitops/charts/keycloak/files/agent-groups.generated.json` | `zuno.access.groups` of every agent |
| MaaS subscriptions | `gitops/charts/models/values.agents.generated.yaml` | groups x model roles the agent may use (ADR-0579 clause 2) |
| Kuadrant RateLimitPolicies / TokenRateLimitPolicies | `gitops/charts/connectivity-link/templates/quota-*.generated.yaml` | corp `quota-policy.yaml` + per-agent `zuno.limits` |
| ai-gateway routing preferences | `gitops/charts/ai-gateway/files/model-routing.generated.yaml` | `zuno.models` per agent and task |
| ai-gateway guardrail modes | `gitops/charts/ai-gateway/files/guardrails-modes.generated.yaml` | corp `guardrails-policy.yaml` + `zuno.guardrails` |
| Per-agent chart values | `gitops/charts/<agent>/values.generated.yaml` | union of the agent's tasks' tools and domains, its groups |
| UnifAI bundles | `gitops/charts/unifai/values.okf.generated.yaml` | agent digests from the corp index, ceilings from the same unions, entitlement mode |
| okf-fetch digest | `gitops/charts/*/values.okf-digest.generated.yaml` | the lock |

A target whose platform component is retired (for example the per-agent
charts after WP-156, or the quota budgets after ADR-0570) is dropped from
the table by the WP that retires it.

**3. Generated files are never edited by hand.** `generate_stack_config.py
--check` runs in `lint.yml` and in the promotion workflow (ADR-0580 clause
2), and fails when any generated file differs from what the locked release
produces. Hand-written values that remain (non-agent groups, platform
quotas, model resources) stay in the existing files; charts merge both.

**4. Keycloak groups are reconciled, not imported.** The ADR-0530 reconcile
Job is extended to create and update the generated `agent_<name>` groups.
It never deletes a group, and never touches membership: membership is a
user-administration act, not an agent definition. A group present in Keycloak
but absent from the release is reported.

**5. The generator interprets OKF; nothing else in the stack does.** It
reads the bundle schema versions ADR-0579 allows and emits plain platform
configuration, so charts, Kuadrant, MaaS and Keycloak never learn OKF. This
is the same isolation principle as ADR-0564 clause 6 and ADR-0508.

## Consequences

Adding an agent, a tool or a group becomes a change in `zuno-demo-agents`
followed by one promotion PR whose diff shows every derived change. The
hand-copied values and the hand-pinned UnifAI digests disappear.

The generated files are many and the PR diff is large; the semantic summary
of ADR-0580 clause 2 is what reviewers read first.

## Security considerations

Generation can widen enforcement only within what the corp policies allow,
and the corp policies are themselves part of the reviewed release. The
platform keeps hard limits that no release can exceed: the contract
(ADR-0576 clause 4) and the hand-written platform quotas.

The Keycloak reconcile Job gains rights to manage groups; it keeps the
ADR-0530 scoping (one client, realm `zuno`) and never manages members.

## Operational considerations

The generator runs offline once the artifacts are pulled. Applying the
result is the ordinary Argo CD sync of the touched Applications; the
Keycloak Job runs as a sync hook, as it already does.

## Amendment (2026-10-25) - generated MaaS subscriptions and model routing

**MaaS subscriptions (clause 2, implemented by WP-164).**
- `gitops/charts/models/values.agents.generated.yaml` lists, for each LOCAL model published through MaaS, the
  entitlement groups of the active agents that can reach it.
- An agent reaches a model when one of its tasks can be routed to it: every catalog model eligible at the
  agent's classification, narrowed by a `strict` routing preference (ADR-0417) and by `forbidden` roles.
- The models chart renders one `<model>-agents` MaaSSubscription owned by all those groups, so a persona
  in several agent groups matches one subscription; MaaS tie-breaking among equal priorities is unverified
  (ADR-0570 clause 3).
- The chart also adds the groups to the model's MaaSAuthPolicy.
- Platform policy stays hand-written: the tier, the `/sales` business-role subscriptions and the
  ServiceAccount subscriptions.
- SaaS models get no persona group (WP-157 decision D5).

**Model routing (clause 2, decided 2026-10-25; code landed 2026-10-25 behind `modelRouting.generated`, not enabled yet, see WP-164).**

The generator writes `gitops/charts/ai-gateway/files/model-routing.generated.yaml`. It uses the schema
`app/model_routing_policy.py` already loads, and the ai-gateway chart mounts it at
`MODEL_ROUTING_POLICY_PATH`. The copy baked into the image stays as the fallback, and a routing change no
longer needs an image rebuild. For each `(agent, task)`:

1. **Candidate set.** When the corp policy has an entry, it sets the candidates. An agent never adds a
   model outside it, never loosens `strict`, and never touches `local_only_for` or classification
   eligibility, which ai-gateway keeps applying at runtime.
2. **Order.** The task's `zuno.models.preferred` roles, or else the agent's, move the candidates with
   those roles to the front, in role order. The other candidates follow in corp order. This ordering
   power was granted by the user's decision of 2026-10-25 and amends
   [ADR-0579](0579-extend-okf-to-v0-3-with-skills-model-roles-guardrails-and-limits.md).
3. **Exclusion.** `forbidden` roles, from the task and the agent, become a new `exclude: [catalog names]`
   field. ai-gateway drops those names after the eligibility and `local_only` filtering, before `prefer`
   and `strict`. If no candidate is left, it fails closed with its existing `RoutingError`.
4. **Task without a corp entry.** Its `prefer` list is built from the roles: role order first, then
   catalog order within a role.

`adapters` and `objectives` are copied from the corp file. With release 0.6.1 no entry changes: every
tekos task declares its roles in its corp order, arkos and comage (OKF v0.2) declare none, and no
release declares `forbidden`. A golden test asserts this equality.
