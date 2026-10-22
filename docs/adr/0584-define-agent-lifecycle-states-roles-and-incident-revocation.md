# ADR-0584: Define agent lifecycle states, roles and incident revocation

- **Status:** Proposed
- **Target:** v0.12
- **Date:** 2026-10-22
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0576](0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md) (review and CODEOWNERS), [ADR-0578](0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md), [ADR-0580](0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md)
- **Related:** [ADR-0564](0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md), [ADR-0106](0106-enforce-okf-bundle-signing-and-validation.md), [ADR-0327](0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md), [ADR-0582](0582-serve-a-per-agent-entry-and-descriptive-sheet-from-the-admitted-bundle.md), [ADR-0583](0583-require-group-visibility-and-object-level-authorisation-before-per-agent-entries.md)

## Context

The decisions that now govern an agent are spread over several records:
authoring and review in `zuno-demo-agents` (ADR-0576), keyless signing by
workflow identity (ADR-0578), promotion of a digest by pull request
(ADR-0580), admission and reconciliation by the unifai-operator (ADR-0564).
None of them says who is accountable for an agent over its whole life, which
states an agent can be in, or how a compromised or faulty agent is switched
off quickly. The only decision owner named in the records is the architecture
team. `status` takes values such as `active` and `placeholder`; nothing
defines `deprecated` or `retired`, nor what happens to a running session when
a workflow disappears (ADR-0564 marks it unverified). There is no
revocation path faster than a new signed release, and no audit event for
activating or retiring an agent.

## Decision

**An agent has an owner, a state machine and a fast switch, and every step is
recorded.**

1. **Roles.** *Agent owner*: accountable for one agent's content and its
   continued use; named in the bundle (`maintainer`) and in CODEOWNERS of
   `zuno-demo-agents`. *Platform team* (the architecture team): accountable
   for the contract, the pin, the operator and the release. *Security
   reviewer*: consulted on every change to `access`, `allowed_*`,
   classification, `local_only_for` and quota class, and responsible for
   incident revocation. These two roles are new and are assigned by the
   decision owners before this ADR is accepted.
2. **Responsibility matrix** (R responsible, A accountable, C consulted, I
   informed):

   | Step | Agent owner | Platform | Security | Signer workflow | Operator | Argo CD |
   |---|---|---|---|---|---|---|
   | Author or change the bundle | R | A | C | - | - | - |
   | Review (schema, policy, generated matrix) | C | A/R | C | - | - | - |
   | Sign and publish (ADR-0578) | - | A | I | R | - | - |
   | Promote the digest (ADR-0580) | I | A/R | C | - | - | I |
   | Verify, validate, emit objects | - | I | - | - | R | - |
   | Apply the custom resource | - | A | - | - | - | R |
   | Activate or change state | R | A | C | - | R | I |
   | Deprecate or retire | R | A | I | - | R | R |
   | Incident revocation | I | A | R | - | R | R |

3. **States.** `placeholder`, `active`, `deprecated`, `retired`. `deprecated`
   keeps the agent usable and marks its sheet; `retired` removes its entry
   and its objects. A state change is a reviewed pull request (ADR-0576
   clause 5), never an edit in the cluster.
4. **Sessions on retirement.** Retirement of an agent ends new executions at
   once; existing sessions stay readable by their owner and cannot resume.
   The behaviour is verified in the pilot before `retired` is used.
5. **Incident revocation.** A revocation switch exists independent of a new
   release: the operator treats an agent listed in a platform-owned
   revocation list (a ConfigMap managed through GitOps) as not admitted and
   removes or disables its entry and objects. A trusted-identity change (a
   compromised signing workflow) is handled by changing the trust policy
   of ADR-0578. Both are documented in a runbook with a response target.
6. **Audit.** The operator emits an event for admission, state change,
   revocation and rejection, with the digest, the actor identity from the
   pull request and the reason. Consultation of a sheet is not audited
   per view; the OpenTelemetry traces of ADR-0566 carry usage.
7. **Separation.** The author of a change to access or classification fields
   cannot be its only approver; CODEOWNERS enforce a second reviewer.

## Consequences

Ownership becomes explicit and reviewable, and a bad agent can be disabled
within one reconciliation cycle instead of a signed release. The operator
gains a revocation list and events; the OKF schema gains the state values.

## Security considerations

The revocation list is a high-value control: only the platform and security
roles may change it, through reviewed pull requests, and the operator must
fail safe (an unreadable list blocks new admissions rather than admitting
all). Branch protection and CODEOWNERS on `zuno-demo-agents` are
preconditions already set by ADR-0576.

## Operational considerations

Role assignment and the runbook are human actions confirmed by the decision
owners. The operator work follows the release flow of the fork. The state
values and the revocation list are checked in the pilot before they are used
on demo222.
