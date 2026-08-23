# ADR-0218: Drop the Aramis ingestion adapter and defer the Salesforce ingestion cadence

- **Status:** Proposed
- **Target:** Unscheduled (backlog) — deliberately outside the v0.1–v0.4 version bands; resumes only under a future ADR if a Salesforce ingestion-cadence need re-emerges
- **Date:** 2026-08-23
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0105](0105-automate-source-specific-knowledge-ingestion.md) (Salesforce/Aramis clauses only) and [ADR-0204](0204-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md) (the `Salesforce -> knowledge.sales` / `Aramis -> knowledge.adv` source-adapter mapping bullets only) — both ADRs otherwise stand unchanged.

## Context

WP-22 (`docs/roadmap/work-packages/wp-22-ingestion-adapters-cadences.md`) built `fetch-salesforce` and `fetch-aramis` source adapters for the generic RAG-ingestion framework ADR-0204 defines, and ADR-0105 promoted per-source cadence scheduling (weekly tech, hours-scale sales, on-demand legacy) to a full decision. Both have sat `Operator pending` since 2026-08-17: Salesforce blocked on real credentials, Aramis blocked because no `ExternalSecret` was ever even attempted for it.

Aramis will not be made available as a service. Continuing to carry it as an open acceptance objective across WP-22/ADR-0105/ADR-0204 misrepresents the roadmap. Separately, Salesforce's batch/indexed ingestion cadence is not needed on the v0.1/v0.2 timeline — Comage's live, tool-based Salesforce access (ADR-0017/ADR-0206/ADR-0208) and the already-provisioned `knowledge.sales` domain/database binding (ADR-0204 part 1, delivered under WP-21) are unaffected and continue to stand; only the automated batch-ingestion half is being pulled out of scope.

## Decision

1. **Aramis is dropped as a source-adapter objective everywhere in WP-22's scope.** No further `fetch-aramis` cadence or credential work is pursued. The already-merged `fetch-aramis` fixture-tested code in `components/rag-ingestion/` is left in place, inert — this decision does not require deleting it, only removing it as a tracked objective.

2. **Salesforce's batch/indexed RAG-ingestion cadence is deferred, unscheduled.** The `fetch-salesforce` adapter and its hours-scale KFP recurring-run schedule are pulled out of v0.1/v0.2 versioned scope and placed in an unscheduled backlog — not v0.4 (that band, ADR-0401–0409, is fully committed to agent-to-agent delegation and has no ingestion-adapter slot; see [0400-v0.4-roadmap.md](0400-v0.4-roadmap.md)). This ADR is the backlog record; there is no companion tracker phase because there is no scheduled work to track.

3. **Unaffected by this decision:** the `knowledge.sales` domain and its dedicated database binding (ADR-0204 part 1 / WP-21, already live); Comage's live Salesforce MCP-tool access (ADR-0017, ADR-0206, ADR-0208); the `load-sxa-dump` adapter and legacy/tech cadences (ADR-0105's remaining scope).

4. **Explicitly out of scope for this ADR:** ADR-0202, ADR-0205 and ADR-0209 also reference Aramis as `knowledge.adv`'s data source, and ADR-0326/WP-35/WP-36 (the Advantage agent) depend on it operationally. None of those are touched here — Advantage's own knowledge-sourcing question is a separate future decision for whoever owns that slice, since Aramis's unavailability affects it too but this ADR does not decide that.

## Consequences

WP-22's remaining scope shrinks to the legacy/tech cadence work already merged — no Salesforce or Aramis credentials block anything further in v0.1/v0.2. `knowledge.adv` has no ingestion adapter of any kind after this decision; any future Advantage-slice work that assumes Aramis-sourced content needs its own ADR to either find a replacement source or accept the gap. Reviving Salesforce ingestion automation later requires a new ADR, not reopening ADR-0105/ADR-0204.

## Security considerations

No change — dropping an adapter that was never provisioned with live credentials has no security posture to unwind. The `knowledge.sales` domain's existing isolation (ADR-0204) is untouched.

## Operational considerations

`ExternalSecret`/cadence scaffolding already merged for Salesforce and Aramis in `gitops/charts/rag-ingestion/` remains shipped `enabled: false` and inert; no removal is required for this decision to take effect, since neither was ever activated.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0105](0105-automate-source-specific-knowledge-ingestion.md)
- [ADR-0202](0202-introduce-logical-knowledge-domains.md)
- [ADR-0204](0204-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md)
- [ADR-0206](0206-separate-current-salesforce-knowledge-from-legacy-sxa.md)
- [ADR-0217](0217-ingest-weekly-anonymized-sxa-corpus-as-a-new-rag-domain.md) — nearest precedent for a partial-supersede note
