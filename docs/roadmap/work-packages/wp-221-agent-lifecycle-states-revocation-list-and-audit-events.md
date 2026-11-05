# WP-221: Agent lifecycle states, revocation list and audit events

- **State:** Not started
- **ADRs:** [ADR-0584](../../adr/0584-define-agent-lifecycle-states-roles-and-incident-revocation.md)
- **Depends on:** [WP-167](wp-167-per-agent-entry-and-sheet.md) (done: the sheet already shows the state)
- **Related:** [ADR-0582](../../adr/0582-serve-a-per-agent-entry-and-descriptive-sheet-from-the-admitted-bundle.md), [ADR-0578](../../adr/0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md), [ADR-0575](../../adr/0575-upstream-generic-unifai-changes-and-isolate-zuno-specific-code.md)
- **Target:** v0.15
- **Estimated files touched:** ~12 in the UnifAI fork (operator state handling, the revocation list, events, tests, sent as a patch to the fork session) and ~5 in `zuno-demo` (the revocation ConfigMap in the unifai chart, the OKF schema state values, a runbook, evidence)

> Why: ADR-0584 is Accepted but has no code behind its clauses 3 to 6. Only the `placeholder` and `active` states exist. This WP builds the rest, so that an agent can be deprecated or retired, and withdrawn at once after an incident without waiting for a new release.

## Goal

An agent can be `deprecated` (still usable, marked on its sheet) or `retired` (no new execution, entry and objects removed, existing sessions still readable by their owner but not resumable), and any agent listed in a platform-owned revocation list is treated as not admitted. Each change emits an audit event.

## Steps

1. **States (clause 3).** Add `deprecated` and `retired` to the state values of the OKF schema and the operator mapping. `deprecated` keeps the agent usable and marks its sheet; `retired` removes its entry and its objects. A state change is a reviewed pull request in `zuno-demo-agents`, never an edit in the cluster.
2. **Sessions on retirement (clause 4).** Retirement ends new executions at once; existing sessions stay readable by their owner and cannot resume. Verify this in a pilot on demo333 before `retired` is used, and write the result to an evidence file.
3. **Revocation list (clause 5).** A ConfigMap managed through GitOps in the `unifai` chart lists agents to revoke. The operator reads it (never writes) and treats a listed agent as not admitted: it removes or disables its entry and objects, without a new release. A compromised signing identity is handled by changing the trust policy of ADR-0578, as the ADR says.
4. **Audit events (clause 6).** The operator emits an event for admission, state change, revocation and rejection, with the digest, the actor identity from the pull request and the reason. Sheet views are not audited per view.
5. **Runbook (clause 5).** Write the incident revocation runbook with a response target, in `docs/`.
6. **Fork change.** Steps 1 to 4 on the operator side are a change to the UnifAI fork on a feature branch (ADR-0575). The fork session writes it itself (envtest, CRD generation and the validator are fork-internal) and this repository reviews the contract; a release is then pinned with the user's go.

## Acceptance

- A bundle set to `deprecated` stays usable and its sheet says so; one set to `retired` disappears from the entry and refuses new executions while the owner can still read the old sessions.
- Adding an agent to the revocation list removes its entry and objects within one reconcile, with no release, and an event records it.
- The runbook exists and the revocation was rehearsed once on demo333.
- ADR-0584 can then move to `Implemented`.

## What the operator has today (2026-11-05, from the fork session's read of `fork/unifai-operator`)

- **No lifecycle state.** `UnifaiAgentBundle` has no state. Its spec carries source, verify, ceilings, entitlement, llm and mcp; its status carries the conditions `Verified`, `Valid`, `WithinCeilings`, `Emitted` and the phase. The nearest patterns are the `spec.suspend` boolean (on `UnifaiRAGSource`, `UnifaiWorkflow` and the stack CronJobs) and the phase `Suspended`. So `deprecated` and `retired` would be a new enum on the bundle spec (for example `spec.lifecycle`) with a status condition, and `retired` would use the same cleanup path as a deletion: the emitted objects are removed.
- **No revocation list.** The operator reads no ConfigMap in the bundle pipeline. It would be a new read-only watch (RBAC `get`, `list` and `watch` on one named ConfigMap), a new condition reason `Revoked`, and a requeue of every bundle when the list changes.
- **Events exist.** The operator already records Kubernetes Events through a recorder (`internal/controller/events.go`, source `unifai-operator`), so the admission, state, revocation and rejection events fit there. The digest and the reason are easy. **The actor from the pull request is not known to the operator:** it has to arrive in a field or an annotation that the GitOps flow writes. This contract point is for this repository to define.

## Decisions pending on the fork side

- The priority against the A2A approval work (the fork's R-535) and the fork's 0.1 freeze on 2026-12-01. This is a CRD change, so it is a candidate for 0.2 unless it turns out small.
- The fork session opens a ROADMAP row when the user says go. Nothing is built before that.
