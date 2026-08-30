# ADR-0533: Consolidate Advantage's and Finage's non-promotion into a dedicated decision

- **Status:** Proposed
- **Target:** v0.8
- **Date:** 2026-08-30
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0326 (v0.3) generalized the Tekos vertical slice to the four remaining
agents. By 2026-08-30 the four slices' repo work and live acceptance gates
had all run (WP-31/33/35/36): Arkos and Comage genuinely reached `active`,
while Advantage and Finage deliberately stayed `placeholder`.

The two agents' non-promotion decisions are recorded asymmetrically today:

- Advantage's is a full ADR: [ADR-0532](0532-accept-knowledge-adv-as-sourceless-pending-a-replacement-adapter.md)
  — `knowledge.adv` stays sourceless pending a replacement ingestion adapter.
- Finage's is only an inline note ("D10") in
  [WP-36](../roadmap/work-packages/wp-36-finage-slice.md) — never formalized
  as its own ADR: Finage's real value is the deterministic `sxa.*`
  capability set over `knowledge.project`, not a new finance RAG domain,
  because `policies/knowledge/knowledge-policy.yaml`'s `knowledge.sxa-legacy`
  entry deliberately excludes `finance` from `allowed_groups` (ADR-0340's
  access-intent table, WP-32) and no finance-specific RAG domain exists in
  this repository.

ADR-0326 was carrying both agents' non-promotion prose inline as well,
which mixed a v0.3 decision that was fully delivered (Arkos/Comage reaching
`active`) with two open-ended non-promotion postures that have no natural
end date. This ADR gives Advantage's and Finage's placeholder status a
single, dedicated, forward-tracked home instead.

## Decision

1. **Advantage stays `zuno.status: placeholder`.** This restates
   [ADR-0532](0532-accept-knowledge-adv-as-sourceless-pending-a-replacement-adapter.md)'s
   decision 2 without changing it; ADR-0532 remains the authoritative
   technical record for *why* (`knowledge.adv` has no source, no cadence, no
   adapter).
2. **Finage stays `zuno.status: placeholder`, formalized here for the first
   time.** Finage's real value is the deterministic `sxa.*` capability set
   (`sxa.customer.read`, `sxa.quote.read`,
   `sxa.aggregate.revenue-by-year`, `sxa.record.lookup`) exercised over
   `knowledge.project`, not a new finance RAG domain. This is WP-36's own
   D10 decision, promoted from an inline work-package note to an ADR-level
   record. `evaluations/finage/scenarios.yaml`'s 20 scenarios are, like
   Advantage's, explicitly written for placeholder behavior and were
   live-verified against that posture, not against active-agent behavior.
3. **Future promotion of either agent is an open question, tracked at v0.8.**
   No replacement `knowledge.adv` source and no finance RAG domain has been
   proposed or evaluated. Evaluating candidates for either is out of scope
   for this decision. A future ADR that wants either agent to answer real
   ADV or finance-domain questions must supersede the relevant part of this
   record (or ADR-0532, for Advantage's sourcing question specifically) with
   a concrete source and its classification default, then rewrite the
   affected agent's `evaluations/*/scenarios.yaml` to test active-agent
   behavior instead of placeholder-blocking behavior — a nontrivial rewrite,
   since several of each agent's 20 scenarios currently assert the agent is
   blocked.

## Consequences

[ADR-0326](0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md)
is trimmed to remove the Advantage/Finage-specific status prose it was
carrying inline, replaced with a pointer to this ADR; it stays scoped to
what it actually delivered for v0.3 (Arkos and Comage reaching `active`).
[ADR-0532](0532-accept-knowledge-adv-as-sourceless-pending-a-replacement-adapter.md)
is unchanged in its own Decision text and remains the authoritative record
for Advantage's sourcing question; it gains a cross-reference to this ADR
as the joint placeholder-tracking record for both agents.

Neither agent's operational posture changes: Advantage and Finage continue
to report `placeholder`/"coming soon" and neither serves live chat traffic.

## Security considerations

None. No new data source, credential or ingestion path is introduced for
either agent. Both agents' existing isolation (dedicated `rag-adv` binding
for Advantage per ADR-0204; `finance` group access scoped to
`knowledge.project`/`sxa.*` capabilities only for Finage per ADR-0340) is
unchanged.

## Operational considerations

Nothing changes operationally for either agent. Operators should not expect
Advantage to answer real ADV questions, or Finage to answer questions
outside its deterministic `sxa.*`/`knowledge.project` scope, until a future
ADR adopts a source for one or the other. Both portal tiles correctly
continue to show "coming soon."

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0326](0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md) — the slice-generalization ADR this consolidates Advantage's and Finage's non-promotion out of
- [ADR-0532](0532-accept-knowledge-adv-as-sourceless-pending-a-replacement-adapter.md) — Advantage's own sourcing decision, still authoritative, cross-referenced here
- [ADR-0218](0218-drop-aramis-adapter-and-defer-salesforce-ingestion-cadence.md) — dropped `knowledge.adv`'s only ingestion adapter
- [ADR-0340](0340-extend-business-role-authorization-with-cdp-and-scoped-capabilities.md) — the access-intent table excluding `finance` from `knowledge.sxa-legacy`
