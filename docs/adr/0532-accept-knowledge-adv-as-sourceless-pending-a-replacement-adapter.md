# ADR-0532: Accept `knowledge.adv` as sourceless pending a replacement adapter

- **Status:** Implemented (2026-08-30)
- **Target:** v0.3
- **Date:** 2026-08-30
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0218 (2026-08-26) dropped the Aramis ingestion adapter entirely and left
`knowledge.adv` with a valid domain descriptor, policy entry and dedicated
`rag-adv` database binding, but no source class, no cadence and no adapter
writing to it — the same "no ingestion pipeline at all" shape
`knowledge.project` already uses, for a different reason. That ADR was
explicit it did not decide Advantage's own sourcing question (its Decision
5): "Advantage's own knowledge-sourcing question is a separate future
decision for whoever owns that slice... Restoring any adv ingestion requires
a new ADR, which is where a replacement source and its classification
default would be decided."

ADR-0326/WP-35 (Advantage vertical slice) is the owner referenced there.
Running WP-35's retroactive PROMOTION.md gate catch-up on 2026-08-30
confirmed empirically what ADR-0218 already implied: `evaluations/advantage/scenarios.yaml`
is authored around the agent's current `placeholder` status (its own
scenario titles say "agent is placeholder-status"), and Agent Runtime does
not register `advantage` as a chat-capable agent while it stays
`placeholder`. No replacement source for `knowledge.adv` has been proposed
or evaluated in the roughly four days since ADR-0218 shipped, and none is
in scope for v0.3.

## Decision

1. **`knowledge.adv` stays sourceless.** No replacement ingestion adapter is
   selected in this ADR. The domain descriptor, policy entry and `rag-adv`
   binding ADR-0218 retained continue to stand unchanged, exactly as
   `knowledge.project` already demonstrates a valid empty-domain shape can.
2. **Advantage stays `zuno.status: placeholder`.** ADR-0326's "mandatory
   common completion pattern" and its acceptance criteria are read as
   requiring each agent to either reach `active` through the full pattern
   or to have its non-promotion formally decided, not as requiring all four
   agents to reach `active` unconditionally. Advantage's repo-side bundle,
   deployment surface (frontend/BFF, Keycloak entitlement) and
   placeholder-scoped evaluation gate (`evaluations/advantage/`, proving the
   agent correctly stays blocked) are complete and live-verified; only the
   data source a genuinely active agent would need remains undecided.
3. **This ADR does not pick a replacement source.** Evaluating specific
   candidates (a new external system, a manual/curated corpus, folding ADV
   content into an existing domain) is out of scope here — this decision
   only closes the "requires its own ADR" pointer ADR-0218 left open by
   making the acceptance of the current gap explicit and reviewed, rather
   than leaving it as a silent, undated omission. A future ADR may propose
   and adopt a real source; this one does not block that.

## Consequences

WP-35 closes as Done on what the repository can independently verify:
real OKF bundle, deployment surface, Keycloak wiring, and a live-run
20-scenario gate proving the placeholder posture behaves correctly — without
waiting on a data-source decision this ADR deliberately does not make.
ADR-0326 can close to Implemented with Advantage correctly documented as
staying non-`active` by decision, not as a residual unfinished gate.

Any future work that wants Advantage to actually answer ADV/bid questions
from real content must first supersede this ADR (or issue a new one) with a
concrete source and its classification default, then rewrite
`evaluations/advantage/scenarios.yaml` to test active-agent behavior instead
of placeholder-blocking behavior — that rewrite is itself nontrivial (at
least 3 of its 20 scenarios currently assert the agent is blocked) and is
not started by this decision.

[ADR-0533](0533-consolidate-advantage-and-finage-non-promotion-into-a-dedicated-decision.md)
(2026-08-30) consolidates this decision's "Advantage stays `placeholder`"
outcome alongside Finage's equivalent, formalized-for-the-first-time
non-promotion decision, into a single v0.8-tracked record. It does not
change or supersede this ADR's own decision on `knowledge.adv`'s sourcing,
which remains authoritative.

## Security considerations

None. No new data source, credential or ingestion path is introduced. The
domain's existing isolation (dedicated `rag-adv` binding, ADR-0204) is
unchanged, and Advantage remains unable to serve live chat traffic while
`placeholder`, which is a stricter posture than any policy this ADR could
loosen.

## Operational considerations

Nothing changes operationally: `knowledge.adv` was already unwritten before
this decision. Operators should not expect Advantage to answer real ADV
questions until a future ADR adopts a source; the portal tile correctly
continues to show "coming soon."

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0218](0218-drop-aramis-adapter-and-defer-salesforce-ingestion-cadence.md) — the decision this one closes the open pointer from (Decision 2/5)
- [ADR-0326](0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md) — the slice-generalization ADR this closes out for Advantage
- [ADR-0533](0533-consolidate-advantage-and-finage-non-promotion-into-a-dedicated-decision.md) — consolidates this decision alongside Finage's equivalent non-promotion decision
- [ADR-0202](0202-introduce-logical-knowledge-domains.md)
- [ADR-0204](0204-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md)
