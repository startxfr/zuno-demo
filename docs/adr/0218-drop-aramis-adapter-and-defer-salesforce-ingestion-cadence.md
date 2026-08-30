# ADR-0218: Drop the Aramis ingestion adapter and defer the Salesforce ingestion cadence

- **Status:** Implemented (2026-08-26) - the Aramis adapter and every trace of its wiring are removed from the repository (see Decision 1); the Salesforce cadence deferral is realized as a v0.6 target.
- **Target:** v0.6 (retargeted from v0.7 on 2026-08-30 — v0.7 split into a short-term closeout band (v0.6) and a long-term/harder band (v0.7); this item and its already-closed siblings ADR-0105/ADR-0206/ADR-0213 move to v0.6, while ADR-0111/ADR-0115 (externally blocked) and ADR-0352 (large not-started effort) remain in v0.7. Previously retargeted from `Unscheduled (backlog)` on 2026-08-26 - roadmap reprioritization, grouped into v0.7's second deferred-items set alongside ADR-0105/ADR-0206/ADR-0213, unrelated to WP-04's GitHub-Actions release-automation theme)
- **Date:** 2026-08-23 (amended 2026-08-26)
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0105](0105-automate-source-specific-knowledge-ingestion.md) (Salesforce/Aramis clauses only) and [ADR-0204](0204-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md) (the `Salesforce -> knowledge.sales` / `Aramis -> knowledge.adv` source-adapter mapping bullets only) - both ADRs otherwise stand unchanged.

## Context

WP-22 (`docs/roadmap/work-packages/wp-22-ingestion-adapters-cadences.md`) built `fetch-salesforce` and `fetch-aramis` source adapters for the generic RAG-ingestion framework ADR-0204 defines, and ADR-0105 promoted per-source cadence scheduling (weekly tech, hours-scale sales, on-demand legacy) to a full decision. Both have sat `Operator pending` since 2026-08-17: Salesforce blocked on real credentials, Aramis blocked because no `ExternalSecret` was ever even attempted for it.

Aramis will not be made available as a service. Continuing to carry it as an open acceptance objective across WP-22/ADR-0105/ADR-0204 misrepresents the roadmap. Separately, Salesforce's batch/indexed ingestion cadence is not needed on the v0.1/v0.2 timeline - Comage's live, tool-based Salesforce access (ADR-0017/ADR-0206/ADR-0208) and the already-provisioned `knowledge.sales` domain/database binding (ADR-0204 part 1, delivered under WP-21) are unaffected and continue to stand; only the automated batch-ingestion half is being pulled out of scope.

The 2026-08-26 amendment sharpens both halves. The original text dropped Aramis as a *tracked objective* while deliberately leaving its code in the tree, and parked Salesforce in an unscheduled backlog. Neither held up: dead adapter code, Vault seeds, `ExternalSecret` templates and KFP pipeline wiring for a source that will never exist is a standing review and maintenance cost with no payoff, and `Unscheduled` was the only such target in the entire ADR index - a target nobody plans against. The Aramis half is now enacted in the repository, and the Salesforce half has a real band.

## Decision

1. **Aramis is dropped as a source-adapter objective everywhere in WP-22's scope, and its implementation is removed from the repository** (amended 2026-08-26 - the original text left the code in place, inert). No further `fetch-aramis` cadence or credential work is pursued, and nothing named `aramis` survives outside this record and the historical notes that cite it. Removed: `_fetch_aramis` plus its `STAGES`/`SOURCE_ADAPTERS`/`IngestionConfig` wiring and fixture test in `components/rag-ingestion/`; the `domains.adv` entry, `aramis` `ExternalSecret`, `ARAMIS_SOURCES_JSON` ConfigMap keys, KFP pipeline component and `fetchStages` schema enum value in `gitops/charts/rag-ingestion/`; the `zuno/aramis/technical` Vault seed and its `zuno_aramis_*` variables in `ansible/`; the Aramis source class in `knowledge/adv/domain.yaml` and the example values in `knowledge/metadata-schema.yaml`; the `domains.adv` pointer in `platform/bindings/knowledge/bindings.yaml`; and the Aramis attributions in `agents/advantage/`.

2. **`knowledge.adv` survives; only its ingestion does not.** The domain descriptor (`knowledge/adv/domain.yaml`), its policy entry and its dedicated `rag-adv` database binding are retained, restated to declare no source class, no cadence and no ingestion adapter - the same "no source ingestion pipeline at all" shape `knowledge.project` already uses, for a different reason. Advantage therefore keeps a valid declared domain that nothing currently writes to. Restoring any adv ingestion requires a new ADR, which is where a replacement source and its classification default would be decided.

3. **Salesforce's batch/indexed RAG-ingestion cadence is deferred to v0.7** (amended 2026-08-26 - previously an unscheduled backlog). The `fetch-salesforce` adapter and its hours-scale KFP recurring-run schedule are pulled out of v0.1/v0.2 versioned scope and land in the v0.7 band, joining the deferred-items group (ADR-0105/ADR-0206/ADR-0213) carried there on 2026-08-26 as a roadmap reprioritization - explicitly *not* part of that band's GitHub-Actions release-automation goal, and still not v0.4 (that band, ADR-0401-0409, is fully committed to agent-to-agent delegation and has no ingestion-adapter slot; see [../roadmap/adr-decisions-v0.4.md](../roadmap/adr-decisions-v0.4.md)). Unlike Aramis, Salesforce is deferred, not dropped: `fetch-salesforce`, `domains.sales` (`enabled: false`) and the `zuno/salesforce/technical` Vault seed all stay in the tree exactly as merged.

4. **Unaffected by this decision:** the `knowledge.sales` domain and its dedicated database binding (ADR-0204 part 1 / WP-21, already live); Comage's live Salesforce MCP-tool access (ADR-0017, ADR-0206, ADR-0208); the `load-sxa-dump` adapter and legacy/tech cadences (ADR-0105's remaining scope). Finage's negative security assertions (`evaluations/finage/security_checks.py`, `agents/finage/`) that it declares no `salesforce.*`/`aramis.*` capability are deliberately left intact - a dropped capability namespace should still be forbidden.

5. **Explicitly out of scope for this ADR:** ADR-0202, ADR-0205 and ADR-0209 also reference Aramis as `knowledge.adv`'s data source, and ADR-0326/WP-35/WP-36 (the Advantage agent) depend on it operationally. None of those decision records are touched here - Advantage's own knowledge-sourcing question is a separate future decision for whoever owns that slice, since Aramis's unavailability affects it too but this ADR does not decide that. The amendment does rewrite `agents/advantage/`'s OKF prose so it no longer asserts an Aramis source it does not have, but that is a factual correction to a bundle description, not a sourcing decision: the agent's declared domains, tasks and capabilities are unchanged.

## Consequences

WP-22's remaining scope shrinks to the legacy/tech cadence work already merged - no Salesforce or Aramis credentials block anything further in v0.1/v0.2. `knowledge.adv` has no ingestion adapter of any kind after this decision; any future Advantage-slice work that assumes Aramis-sourced content needs its own ADR to either find a replacement source or accept the gap. Reviving Salesforce ingestion automation later means picking it up in v0.7, not reopening ADR-0105/ADR-0204.

`gitops/charts/rag-ingestion/values.schema.json`'s `fetchStages` enum no longer accepts `fetch-aramis`, so any out-of-tree values file still naming it now fails `helm lint` rather than silently rendering a stage the image cannot run. Likewise `rag_ingestion.py` no longer accepts `fetch-aramis` as a stage argument at all.

## Security considerations

No change. Dropping an adapter that was never provisioned with live credentials has no security posture to unwind, and the removal only shrinks the credential surface: one Vault path (`zuno/aramis/technical`) that was never populated is no longer seeded, and one `ExternalSecret` that never synced is no longer rendered. The `knowledge.sales` and `knowledge.adv` domains' existing isolation (ADR-0204) is untouched - `knowledge.adv` keeps its dedicated database and credential prefix even with no writer.

## Operational considerations

Nothing live changes. `domains.adv` shipped `enabled: false` and was never activated, so removing it deploys as a no-op; the same holds for the Aramis `ExternalSecret` and the Vault seed, which was skipped on every run while its placeholder remained. Operators who copied `ansible/confidential.example.yml` should drop the now-unused `zuno_aramis_base_url`/`zuno_aramis_token`/`zuno_aramis_enabled` keys from their own `confidential.yml`; leaving them present is harmless but they are read by nothing.

Salesforce's scaffolding is *not* removed: `domains.sales` remains shipped `enabled: false` and inert until its v0.7 work is picked up, and the `zuno/salesforce/technical` seed stays in `ansible/roles/vault/tasks/install.yml`. "Aramis access" is removed from the operator action queue; "Salesforce (sandbox) credentials" stays, marked v0.7-deferred.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0105](0105-automate-source-specific-knowledge-ingestion.md)
- [ADR-0202](0202-introduce-logical-knowledge-domains.md)
- [ADR-0204](0204-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md)
- [ADR-0206](0206-separate-current-salesforce-knowledge-from-legacy-sxa.md)
- [ADR-0217](0217-ingest-a-weekly-sxa-corpus-as-a-new-rag-domain.md) - nearest precedent for a partial-supersede note
