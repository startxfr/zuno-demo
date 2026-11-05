# Runbook: withdrawing an agent after an incident

**Status: draft.** It becomes final when the revocation has been rehearsed once on demo333 (acceptance of
[WP-221](../roadmap/work-packages/wp-221-agent-lifecycle-states-revocation-list-and-audit-events.md)). It implements
[ADR-0584](../adr/0584-define-agent-lifecycle-states-roles-and-incident-revocation.md) clause 5.

## When to use it

An agent must stop being served now, and waiting for a new agents release would take too long: a leaked secret in a
prompt, an unsafe tool, wrong data reaching users, or a compromised release workflow.

## Response target (proposed)

The agent is withdrawn from `zuno-unifai` **within one hour** of the decision. The decision owners confirm or change
this target (ADR-0584, operational considerations).

## Who decides

For the demo platform the agent owner and the security reviewer are both the decision owner of the demo (acceptance note
of ADR-0584). Record the person who approves; that name goes in the `actor` field below.

## The path (once the operator release of WP-221 is pinned)

1. **Write the entry.** In the cluster's file under `ansible/clusters/`, add to `zuno_unifai_values.agentRevocations`:

   ```yaml
   agentRevocations:
     - bundle: tekos                      # the UnifaiAgentBundle name, i.e. the OKF agent name
       reason: "signing identity compromised"
       actor: <who approved>              # all three fields are required
   ```

   The chart refuses an entry without a bundle, a reason or an actor.
2. **Roll it.** Push, then `make d2 install unifai`. The chart writes the ConfigMap `unifai-agent-revocations`
   (key `revoked`) in the bundles' namespace. Editing the ConfigMap by hand does not last: ArgoCD reverts it.
3. **Check.**
   - `oc get unifaiagentbundle <agent> -n zuno-unifai` shows the bundle not admitted, with the reason `Revoked`.
   - The agent's workflows are gone from the team workspace, and `/agents/<agent>` answers "Agent not found".
   - `oc get events -n zuno-unifai` carries the revocation event with the reason and the actor.
4. **Then fix it properly.** Open a pull request in `zuno-demo-agents` that sets `zuno.status: retired` (or fixes the
   content), release it, and promote it. Remove the revocation entry in the same change that pins the release.

## What the operator does with the list

- **Format.** Strict: each entry has `bundle`, `reason` and `actor`, and nothing else. The chart requires all three.
- **Immediate effect.** The ConfigMap carries the label `app.kubernetes.io/part-of: unifai`, which the operator's cache
  watches, so a change is applied within one reconcile. Without the label it would wait for the next resync (10 minutes).
- **A revocation always takes effect,** even with an empty reason: the event and the condition then say "no reason given
  in the revocation list", and the actor reads `unknown`. Only a `retired` bundle without the annotation
  `unifai.startx.fr/reason` is refused (`MissingReason`, its objects are left as they are).
- **An unreadable list** (malformed YAML, an unknown field, an entry without `bundle`) puts the operator in the phase
  `Error` with the reason `RevocationListUnreadable`: nothing new is admitted and what is emitted stays. Fix the list.
- **Events** (source `unifai-operator`): `Admitted`, `StateChanged` (to `deprecated` or `retired`), `Revoked` and
  `Rejected`, each with the digest, the actor and the reason.

## A compromised signing identity

A change of trusted identity is not a revocation-list entry: change the trust policy of
[ADR-0578](../adr/0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md), then
promote a release signed by the new identity.

## Until the operator release is pinned

The list is written but nothing reads it. The fastest withdrawal is a new agents release that sets the agent to
`zuno.status: placeholder`, promoted through `okf-promote`: the operator then stops serving it and removes what it
emitted. Count in hours, not minutes.

## Sessions

An owner keeps access to the sessions of a withdrawn agent only as far as UnifAI allows it; the pilot of WP-221 records
exactly what that is, and this section is completed with the result.
