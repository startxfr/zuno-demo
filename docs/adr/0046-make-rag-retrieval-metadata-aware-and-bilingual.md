# ADR-0046: Make RAG retrieval metadata-aware and bilingual

- **Status:** To be implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The current RAG direction combines pgvector with PostgreSQL full-text search, but Tekos requirements demand explicit product/version selection, source trust, classification, ACL handling, freshness and both French and English content. Similarity alone can return an incorrect OpenShift version even when the user names a version.

## Decision

Attach normalized metadata to every indexed chunk: product, version, language, source/source_type, classification, ACL/tenant scope where applicable, last_modified, stale_after and provenance. Apply deterministic metadata filters before ranking when the user specifies product/version or policy requires them. Support bilingual retrieval and hybrid vector/full-text ranking.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

Tekos can answer version-specific questions more reliably and classification/ACL logic can be enforced at retrieval time.

## Security considerations

Retrieval must never return documents the user cannot access. C2/C3 metadata must propagate into effective classification according to ADR-0034.

## Operational considerations

Add test corpora containing conflicting versions and bilingual content; acceptance tests must prove the requested version is preferred or enforced.

## Implementation state

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0015
- ADR-0109
- ADR-0110
- ADR-0034
- ADR-0035

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
