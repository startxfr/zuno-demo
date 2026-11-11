# WP-221: Agent lifecycle states, revocation list and audit events

- **State:** Operator pending (2026-11-11: the operator part is released in UnifAI v0.1.60, demo333 runs v0.1.68; left: the canary rehearsal on demo333, see Status below)
- **ADRs:** [ADR-0584](../../adr/0584-define-agent-lifecycle-states-roles-and-incident-revocation.md)
- **Depends on:** [WP-167](wp-167-per-agent-entry-and-sheet.md) (done: the sheet already shows the state)
- **Related:** [ADR-0582](../../adr/0582-serve-a-per-agent-entry-and-descriptive-sheet-from-the-admitted-bundle.md), [ADR-0578](../../adr/0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md), [ADR-0575](../../adr/0575-upstream-generic-unifai-changes-and-isolate-zuno-specific-code.md)
- **Target:** v0.15
- **Estimated files touched:** ~12 in the UnifAI fork (operator state handling, the revocation list, events, tests, sent as a patch to the fork session) and ~5 in `zuno-demo` (the revocation ConfigMap in the unifai chart, the OKF schema state values, a runbook, evidence)

> Why: ADR-0584 is Accepted but has no code behind its clauses 3 to 6. Only the `placeholder` and `active` states exist. This WP builds the rest, so that an agent can be deprecated or retired, and withdrawn at once after an incident without waiting for a new release.

## Goal

An agent can be `deprecated` (still usable, marked on its sheet) or `retired` (no new execution, entry and objects removed, existing sessions still readable by their owner but not resumable), and any agent listed in a platform-owned revocation list is treated as not admitted. Each change emits an audit event.

## Steps

1. **States (clause 3).** Add `deprecated` and `retired` to `zuno.status` in the OKF schema of `zuno-demo-agents` (today `placeholder | active`) and to the operator's mapping. There is no new field on the `UnifaiAgentBundle`: the state stays in the reviewed bundle. `deprecated` keeps the agent usable and marks its sheet; `retired` removes its entry and its objects. A state change is a reviewed pull request in `zuno-demo-agents`, never an edit in the cluster.
2. **Sessions on retirement (clause 4).** Retirement ends new executions at once; existing sessions stay readable by their owner and cannot resume. **Verified on 2026-11-05** with no fork change: after the workflow is deleted the session stays in the list and can be opened, and a new message is refused ("The workflow associated with this chat has been deleted and can no longer be continued"). See [the pilot](../evidence/wp-221-session-pilot-2026-11-05.md); the answers of an agent were not part of it.
3. **Revocation list (clause 5).** The ConfigMap `unifai-agent-revocations` (key `revoked`, a YAML list of `{bundle, reason, actor}`), managed through GitOps in the `unifai` chart, in the bundles' namespace, lists agents to revoke. The operator reads it (never writes) and treats a listed agent as not admitted: it removes or disables its entry and objects, without a new release. A compromised signing identity is handled by changing the trust policy of ADR-0578, as the ADR says.
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

## Contract agreed with the fork session (2026-11-05)

- **State.** `zuno.status` gains `deprecated` and `retired` (exact names). The operator maps `deprecated` to "served as today, condition reason `Deprecated`, sheet marked", and `retired` to "not served, emitted objects removed, reason `Retired`", the same path as a placeholder; `spec.servePlaceholder` does not bring a retired agent back. No CRD change.
- **Revocation list.** ConfigMap `unifai-agent-revocations` in the bundles' namespace (`zuno-unifai`), key `revoked`, a YAML list of `{bundle, reason, actor}` where `bundle` is the `UnifaiAgentBundle` name (the OKF agent name). The operator's ClusterRole already reads ConfigMaps cluster-wide, so no RBAC change.
- **Actor and reason.** Annotations `unifai.startx.fr/actor` and `unifai.startx.fr/reason` on the bundle, copied into the Event and the condition, `unknown` when absent. A missing reason on `retired` or on a revocation makes the bundle `Valid=False` with reason `MissingReason`.
- **Sequencing rule.** A bundle that carries `deprecated` or `retired` is refused by the operator until the release that implements this, so no agent is merged in those states in `zuno-demo-agents` before that release is pinned on demo333.
- **Fork tracking.** R-536 in the fork's ROADMAP. With no CRD change it is about one week of work; its slot against R-535 waits for the user's call.

## Decisions (2026-11-05)

- **Go.** The user approved the work, and the fork session writes the operator part.
- **Priority.** The user wants it as early as possible. It is a CRD change, so it lands in the fork's 0.1 line only if it is small enough before the freeze of 2026-12-01; otherwise it is a 0.2 candidate and the fork session says so with a date.
- **Order.** The fork session opens its own ROADMAP row and places it against its other work (R-535, the A2A approval).

## Contract proposed for the actor and the reason

The operator cannot know who approved a state change, so the GitOps flow writes it onto the `UnifaiAgentBundle`:

- `unifai.startx.fr/actor`: who approved the change (the merger of the pull request that changed the state or the revocation list).
- `unifai.startx.fr/reason`: a short reason, required for `retired` and for a revocation.
- The operator copies both into the event it emits and into the status condition, and writes `unknown` when they are absent. The names are generic on purpose: the fork carries no Zuno field (ADR-0575).
- On the zuno-demo side, the promotion flow of the agents release (`.github/workflows/okf-promote.yml`) or the `unifai` chart fills them; the revocation list's own commit gives the actor of a revocation. This is to be reviewed by the fork session before it builds.

## Prepared in zuno-demo and the agents repository (2026-11-05)

- **Agents repository:** branch `wp221-lifecycle-states` of `zuno-demo-agents` adds `deprecated` and `retired` to `zuno.status` in the v0.3 schema. Schema only: no agent changes state, and none may be released as `deprecated` or `retired` before the operator release is pinned.
- **Generator:** `platform/okf/generate_stack_config.py` treats a `deprecated` agent as served (same model reach as `active`) and a `retired` one as not served, with a test.
- **Chart:** the `unifai` chart renders the ConfigMap `unifai-agent-revocations` from `agentRevocations` (empty today; each entry needs a bundle, a reason and an actor). The operator does not read it until the release of R-536.
- **Runbook:** [agent-revocation-runbook.md](../../platform/agent-revocation-runbook.md), a draft until the rehearsal.
- **Annotations (2026-11-05):** the stack-config generator writes `unifai.startx.fr/reason: promoted release vX.Y.Z` on every bundle, and the `unifai` chart renders the annotations of a bundle (a per-agent override goes in `zuno_unifai_bundle_settings.<agent>.annotations`). The operator ignores them until its release. **`unifai.startx.fr/actor` is not written for an ordinary promotion:** nothing in the promotion records who merges the pull request (the PR author is `github-actions[bot]` or whoever started the workflow, and the merger is only known after the merge), so the operator reports `unknown`. A real actor needs a workflow on `pull_request: closed` that reads `merged_by` and commits it, or an explicit `actor` in `zuno_unifai_bundle_settings` for a state change with a named approver.
- **Still to do:** the rehearsal on demo333 once the operator release is pinned, and the evidence. The session pilot is done.

## Session pilot (2026-11-05)

Done: the owner keeps and can open the session of a deleted workflow and cannot resume it, so clause 4 needs nothing from the fork. [Evidence](../evidence/wp-221-session-pilot-2026-11-05.md). Remaining limit: a pilot on a real agent chat would also show whether the agent's answers stay readable.
