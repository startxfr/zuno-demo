# ADR-0039: Make Agent Runtime execute the OKF agent contract

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

Tekos behavior is currently hard-coded in `components/agent-runtime/app/graph/nodes.py`: tool triggers, prompts, default classification and graph selection are code decisions. The OKF definition describes intended behavior but does not yet drive execution, which prevents configuration-only onboarding of a sixth agent.

## Decision

Introduce an `AgentRegistry` that loads, validates and caches signed OKF bundles, resolves agent/task definitions, and produces a typed `AgentDefinition`. Introduce a `GraphFactory` that builds or selects LangGraph workflows from the definition. Prompts, allowed tools, RAG collections, model policy, memory policy, approval requirements and default classification must come from the agent/task contract unless a platform policy overrides them.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

Agent behavior becomes truly declarative and the shared runtime remains generic. Runtime complexity increases because configuration errors must be validated early and reported clearly.

## Security considerations

The registry must validate signatures/schema and enforce platform ceilings. An agent definition can restrict permissions but cannot grant capabilities beyond platform policy.

## Operational considerations

A v0 acceptance test must prove that changing an agent definition changes allowed tools/model/context without modifying runtime source code.

## Implementation state

**Implemented (2026-08-05), scoped to v0's single graph shape.** A new
`components/agent-runtime/app/registry.py` `AgentRegistry` loads,
shape-validates and caches every `agents/<name>/agent.okf.md` bundle
(ADR-0038) under `AGENTS_DIR` at import time, resolving `AgentDefinition`/
`TaskDefinition` objects. `app/graph/nodes.py` now derives from it what
used to be hardcoded Python constants: `TEKOS_BASE_CLASSIFICATION` (was a
literal `"C1"`, now `agents/tekos/agent.okf.md`'s
`zuno.model.preferred_classification`), `RAG_TOP_K` (was a literal `5`,
now `zuno.rag.top_k` - a new bundle field), the `reason` node's system
prompt (was a Python string literal, now
`agents/tekos/prompts/answer-technical-question.md`'s body text), and
whether `tool_call_node` may call `search_confluence` at all (now checked
against `agents/tekos/tasks/answer-technical-question.md`'s
`zuno.allowed_tools` before every call, in addition to the MCP Gateway's
own ADR-0036 enforcement of the same declaration). Loading fails fast at
service startup (raises, not a silent fallback) if the bundle or its
required task/prompt is missing or malformed, per the Security
considerations above ("configuration errors must be validated early").

Honest scope note on "GraphFactory": v0 has exactly one graph shape
(Tekos's retrieve/tool_call/reason/respond LangGraph workflow,
`app/graph/build.py`), so there is no graph-shape *selection* to implement
yet - what this ADR requires (prompts/tools/RAG/classification coming from
the OKF contract rather than code) is fully satisfied by the registry
resolving those values, documented in `build.py`'s module docstring as
where a second graph shape would be added if a second agent goes active.
Platform-ceiling enforcement (Security considerations: "an agent
definition can restrict permissions but cannot grant capabilities beyond
platform policy") is the MCP Gateway's job (ADR-0036), not duplicated here
- this runtime's own `allowed_tools` check is a local fail-fast, not the
authoritative enforcement point.

Mandatory acceptance test (Operational considerations above):
`components/agent-runtime/tests/test_registry.py` - besides sanity-checking
the real Tekos bundle, `test_changing_the_bundle_changes_resolved_behavior_with_no_code_change`
loads a temporary fixture bundle, edits only its task file's
`allowed_tools`, reloads via a fresh `AgentRegistry`, and asserts the
resolved tool list changed - proving runtime behavior is config-driven
using a bundle entirely independent of Tekos's own, not just confirming
Tekos's current values happen to match its own bundle.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0005
- ADR-0006
- ADR-0007
- ADR-0018
- ADR-0022
- ADR-0038

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
