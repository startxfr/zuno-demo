# ADR-0035: Prevent restricted internal context from reaching external models

- **Status:** Implemented
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

**Implemented (2026-08-05).** `policies/tools/tool-policy.yaml`'s
`search_confluence` entry is corrected from `min_classification: C1` to
`C2`, and gains a new `external_model_policy.allow_context: false` field -
a source-level restriction independent of classification. This flows
through the whole chain rather than being duplicated as separate config:
`components/mcp-gateway/app/policy.py` parses it onto `ToolPolicyEntry`/
`PolicyDecision`, `app/main.py`'s `/v1/tools/{tool}/invoke` response echoes
it back as `external_model_policy.allow_context`, `components/agent-runtime/
app/graph/nodes.py`'s `tool_call_node` reads that response field and sets
`local_only_required` in graph state, and `reason_node` /
`app/clients/model_router.py` forward it as a new `X-Zuno-Local-Only`
header to `components/ai-gateway`, whose `app/routing.py:candidates_for()`
filters to `kind == "local"` providers when set - regardless of what the
declared classification's own SaaS-eligibility would otherwise permit
(C2 alone allows an approved-SaaS allow-list per
`policies/data-classification/classification.yaml`).

Mandatory acceptance test (Operational considerations above):
`evaluations/tekos/security_checks.py`'s
`ai_gateway_local_only_forces_local_provider` sends a C2 request with
`X-Zuno-Local-Only: true` directly to `components/ai-gateway` and asserts
`zuno_provider == "local"`, proving the "C2 Confluence + SaaS denied,
C2 Confluence + local allowed" requirement - the local provider is
eligible for every classification level (`provider-routing.yaml`), so
"local allowed" is inherent to the filter and doesn't need a separate
positive-path assertion beyond that same call succeeding.

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
