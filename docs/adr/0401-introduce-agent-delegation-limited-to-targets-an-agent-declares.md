# ADR-0401: Introduce agent-to-agent delegation limited to the targets an agent declares

- **Status:** Proposed
- **Target:** v0.11
- **Date:** 2026-10-24
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md), [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md), [ADR-0326](0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md), [ADR-0402](0402-adopt-a2a-as-the-inter-agent-protocol.md), [ADR-0403](0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md), [ADR-0406](0406-limit-agent-delegation-by-depth-cycle-and-budget.md), [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md), [ADR-0578](0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md), [ADR-0579](0579-extend-okf-to-v0-3-with-skills-model-roles-guardrails-and-limits.md), [ADR-0584](0584-define-agent-lifecycle-states-roles-and-incident-revocation.md)

## Context

This ADR started as a stub (2026-08-13): "Allow approved agent delegation while
preserving identity, budget and policy boundaries." It waited for several agents
to exist; ADR-0326 left delegation to this roadmap.

Eight agents now exist (Tekos, Arkos and Comage `active`; five placeholders).
None declares or uses delegation. The need is real but latent: Tekos hands an
architecture write-up to Arkos today by the user switching agents, and Finage's
prompt tells the user to ask Comage or Advantage. The UnifAI fork already
contains an A2A client node, and nothing in zuno prevents a user of the UnifAI
interface from adding one to a workflow: no rule says which agents may call which.

ADR-0011 does not cover delegation. Applied unchanged, a call from A to B would be
authorized by B's declaration alone, so A could reach any tool B holds. That is a
confused deputy, which this ADR exists to prevent.

## Decision

1. **Delegation is declared, never inferred.** An agent may delegate only to the
   targets listed in its own OKF bundle: `zuno.delegation.targets`, a list of
   `{agent, task}` (ADR-0579 amendment, optional field of v0.3). An agent with no
   such list cannot delegate. The declaration travels in the signed release
   (ADR-0578), so changing it needs a reviewed change to the agents repository.
2. **A target is a real, runnable agent.** The target agent must be `active`
   (ADR-0584): a `placeholder`, `deprecated` or `retired` agent, or one on the
   revocation list, is not a valid target, and a declared target that stops being
   active makes the delegation fail, not fall back.
3. **The user must hold the target's entitlement.** The initiating user must belong
   to one of the target agent's `zuno.access.groups` (ADR-0040), exactly as if the
   user opened that agent. Delegation never grants an entitlement.
4. **The delegating agent does not lend its rights.** The target runs with its own
   declaration and task rights, intersected with the user's, under ADR-0011 as
   amended by ADR-0403. Being declared as a target does not widen the tools of the
   delegator, and the delegator's tools are not consulted for the target's calls.
5. **What comes back is bounded.** A result returned from B to A must not carry a
   classification above the delegating task's own ceiling (ADR-0565); a response
   above it is refused with an error naming the ceiling, never silently downgraded.
6. **Default is no delegation.** Absent field, empty list or unreadable bundle all
   mean refusal. A deployment that never declares a target behaves as today.

## Alternatives considered

- **Any agent may call any agent the user can reach:** rejected. It is the confused
  deputy: nothing records or reviews who may call whom.
- **The target's tools are intersected with the delegator's:** rejected. It defeats
  the purpose: Finage, which cannot reach Salesforce, could never obtain anything
  from Comage, which can.
- **Declare delegation in `tool-policy.yaml` as a tool:** rejected. Delegation is a
  property of an agent and its task, reviewed with its bundle, not of a tool.

## Consequences

- The OKF v0.3 schema gains an optional `zuno.delegation` block, and the narrowing
  rule checks it ([ADR-0406](0406-limit-agent-delegation-by-depth-cycle-and-budget.md)
  gives its ceiling).
- Tekos to Arkos (`draft-architecture-testimonial`) is the first declared pair, on
  demo333 only; nothing else changes until another pair is declared.
- A2A nodes added by hand in the UnifAI interface are refused or put in error by the
  operator until the contract is delivered (WP-173); afterwards the operator emits
  an A2A node only from a declared target.

## Security considerations

The declaration is reviewed and signed content, which is what makes it a policy and
not a convention. The gateway checks it on every delegated call
([ADR-0403](0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md)).
Residual risk and its mitigation are stated there.

## Review evidence

Eight agent bundles and their prompts read on 2026-10-24: no declared delegation
anywhere; the schema `additionalProperties: false` has no delegation field;
`components/mcp-gateway/app/policy.py` evaluates a single agent per call.
