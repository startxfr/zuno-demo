# ADR-0039: Make Agent Runtime execute the OKF agent contract

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

Tekos behavior is currently hard-coded in `components/agent-runtime/app/graph/nodes.py`: tool triggers, prompts, default classification and graph selection are code decisions. The OKF definition describes intended behavior but does not yet drive execution, which prevents configuration-only onboarding of a sixth agent.

## Decision

Introduce an `AgentRegistry` that loads, validates and caches signed OKF bundles, resolves agent/task definitions, and produces a typed `AgentDefinition`. Introduce a `GraphFactory` that builds or selects LangGraph workflows from the definition. Prompts, allowed tools, RAG collections, model policy, memory policy, approval requirements and default classification must come from the agent/task contract unless a platform policy overrides them.

## Consequences

Agent behavior becomes truly declarative and the shared runtime remains generic. Runtime complexity increases because configuration errors must be validated early and reported clearly.

## Security considerations

The registry must validate signatures/schema and enforce platform ceilings. An agent definition can restrict permissions but cannot grant capabilities beyond platform policy.

## Operational considerations

A v0 acceptance test must prove that changing an agent definition changes allowed tools/model/context without modifying runtime source code.

## Implementation state

**Implemented (2026-08-05), scoped to v0's single graph shape.**

- New `components/agent-runtime/app/registry.py` `AgentRegistry` loads, shape-validates and caches every `agents/<name>/agent.okf.md` bundle (ADR-0038) under `AGENTS_DIR` at import time, resolving `AgentDefinition`/`TaskDefinition` objects. `app/graph/nodes.py` now derives from it what used to be hardcoded Python constants: `TEKOS_BASE_CLASSIFICATION` (was literal `"C1"`, now `zuno.model.preferred_classification`), `RAG_TOP_K` (was literal `5`, now `zuno.rag.top_k`, a new bundle field), the `reason` node's system prompt (was a Python string literal, now the prompt document's body text), and whether `tool_call_node` may call `search_confluence` at all (checked against the task's `zuno.allowed_tools` before every call, in addition to the MCP Gateway's own ADR-0036 enforcement). Loading fails fast at service startup (raises, not a silent fallback) if the bundle or its required task/prompt is missing or malformed.
- Scope note on "GraphFactory": v0 has exactly one graph shape (Tekos's retrieve/tool_call/reason/respond LangGraph workflow, `app/graph/build.py`), so there is no graph-shape *selection* to implement yet - what this ADR requires (prompts/tools/RAG/classification coming from the OKF contract) is fully satisfied by the registry, documented in `build.py`'s module docstring as where a second graph shape would be added. Platform-ceiling enforcement is the MCP Gateway's job (ADR-0036), not duplicated here - this runtime's own `allowed_tools` check is a local fail-fast, not the authoritative enforcement point.
- Mandatory acceptance test: `components/agent-runtime/tests/test_registry.py`'s `test_changing_the_bundle_changes_resolved_behavior_with_no_code_change` loads a temporary fixture bundle entirely independent of Tekos's own, edits only its task file's `allowed_tools`, reloads via a fresh `AgentRegistry`, and asserts the resolved tool list changed.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.

## Related ADRs

- ADR-0005
- ADR-0006
- ADR-0007
- ADR-0018
- ADR-0022
- ADR-0038
