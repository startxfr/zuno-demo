# ADR-0035: Prevent restricted internal context from reaching external models

- **Status:** To be implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The project classifies Confluence content as C2, but `policies/tools/tool-policy.yaml` currently declares `search_confluence` with `min_classification: C1`, and Tekos can forward tool excerpts into a C1 reasoning call. The project also requires internal Confluence context not to be sent to external SaaS models.

## Decision

Classify Confluence-derived content as C2 and attach an explicit external-context policy. Content from sources marked `external_model_policy.allow_context: false` must only be processed by approved local inference, regardless of the broader C2 policy. Model routing must evaluate both classification and source-level externalization constraints.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

The policy expresses the difference between sensitivity class and contractual/source restrictions. External providers remain usable for public C1 workloads while internal Confluence excerpts stay local.

## Security considerations

Confluence excerpts, embeddings that can reveal source content, summaries derived from restricted pages and conversation memory containing those excerpts must not cross the external-model boundary.

## Operational considerations

Correct `search_confluence` classification, add source metadata, and add a mandatory acceptance test proving `C2 Confluence + SaaS` is denied while `C2 Confluence + local` is allowed.

## Implementation state

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0021
- ADR-0034
- ADR-0046

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
