# ADR-0035: Prevent restricted internal context from reaching external models

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The project classifies Confluence content as C2, but `policies/tools/tool-policy.yaml` currently declares `search_confluence` with `min_classification: C1`, and Tekos can forward tool excerpts into a C1 reasoning call. The project also requires internal Confluence context not to be sent to external SaaS models.

## Decision

Classify Confluence-derived content as C2 and attach an explicit external-context policy. Content from sources marked `external_model_policy.allow_context: false` must only be processed by approved local inference, regardless of the broader C2 policy. Model routing must evaluate both classification and source-level externalization constraints.

## Consequences

The policy expresses the difference between sensitivity class and contractual/source restrictions. External providers remain usable for public C1 workloads while internal Confluence excerpts stay local.

## Security considerations

Confluence excerpts, embeddings that can reveal source content, summaries derived from restricted pages and conversation memory containing those excerpts must not cross the external-model boundary.

## Operational considerations

Correct `search_confluence` classification, add source metadata, and add a mandatory acceptance test proving `C2 Confluence + SaaS` is denied while `C2 Confluence + local` is allowed.

## Implementation state

**Implemented (2026-08-05).**

- `policies/tools/tool-policy.yaml`'s `search_confluence` entry is corrected from `min_classification: C1` to `C2`, and gains `external_model_policy.allow_context: false` - a source-level restriction independent of classification, flowing through the whole chain rather than duplicated as separate config: `components/mcp-gateway/app/policy.py` parses it onto `ToolPolicyEntry`/`PolicyDecision`; `app/main.py`'s `/v1/tools/{tool}/invoke` response echoes it back; `components/agent-runtime/app/graph/nodes.py`'s `tool_call_node` reads that field and sets `local_only_required` in graph state; `reason_node`/`app/clients/model_router.py` forward it as `X-Zuno-Local-Only` to `components/ai-gateway`, whose `app/routing.py:candidates_for()` filters to `kind == "local"` providers when set, regardless of what the declared classification's own SaaS-eligibility would otherwise permit.
- Mandatory acceptance test: `evaluations/tekos/security_checks.py`'s `ai_gateway_local_only_forces_local_provider` sends a C2 request with `X-Zuno-Local-Only: true` directly to `ai-gateway` and asserts `zuno_provider == "local"` - the local provider is eligible for every classification level (`provider-routing.yaml`), so "local allowed" is inherent to the filter and needs no separate positive-path assertion.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.

## Related ADRs

- ADR-0021
- ADR-0034
- ADR-0046
