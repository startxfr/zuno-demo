# ADR-0401: Introduce agent-to-agent delegation limited to the targets an agent declares

- **Status:** Accepted (2026-10-24) - the decisions below are settled; it becomes `Implemented` once the proofs of "Before Implemented" are made live (WP-174)
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
5. **What comes back raises, never lowers.** A target's result enters the delegator's run at the
   target's classification or higher (ADR-0565's monotone escalation, detailed in ADR-0403 clause 5),
   so a delegation can never be used to carry data into a run handled at a lower level.
6. **Default is no delegation.** Absent field, empty list or unreadable bundle all
   mean refusal. A deployment that never declares a target behaves as today.

## Decisions of 2026-10-24

Taken with the user while closing this record:

- **The target does not consent.** Only the delegating agent declares the delegation. A user who holds
  `agent_arkos` can already use Arkos directly; delegation gives that user nothing more, and one place to
  review is better than two. Rejected: a target-side `accepts_from` field (a second field, a second review
  and a schema release) and a consent required only of sensitive targets (two rules to explain and test).
- **A target is an agent and a task** (`{agent, task}`), never a whole agent: the least privilege, and a task
  added later by another team is not reachable until the delegator has reviewed it.
- **The return rule is proved, not only specified.** "What comes back raises, never lowers" (clause 5) is kept
  by the agents' runs in the UnifAI fork (WP-173), because the gateway cannot see the delegator's run. The
  proof is an acceptance criterion of WP-174, below. Rejected: relying on the fork's unit tests alone, and an
  independent check in the ai-gateway (it does not see the chain, so it would need a new header and new code).

## Before Implemented

On demo333, as an `eval-*` persona: a Tekos run (C1) that receives a result from Arkos (C3) continues at C3,
so the ai-gateway floor and the local-only rules (ADR-0035, ADR-0550) apply to it; and the refusals of WP-174
(unentitled user, undeclared target, depth, cycle) hold. Prerequisites of the first live delegation are listed
in [ADR-0403](0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md).

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
- Arkos to Tekos (`answer-technical-question`) is the first declared pair, on
  demo333 only; nothing else changes until another pair is declared. (Amended
  2026-11-01: the first pair was Tekos to Arkos; it was reversed because Tekos's
  skills serve Arkos's users and not the other way round. Arkos is already C3/local-only,
  so the static C3 raise of a delegating task costs nothing there, whereas it would have
  moved every Tekos turn to a local model.)
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
