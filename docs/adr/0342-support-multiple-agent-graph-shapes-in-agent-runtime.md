# ADR-0342: Support multiple agent graph shapes in Agent Runtime

- **Status:** Partially implemented (shape registry, generic dispatch, fail-fast validation and tests merged; Arkos second shape pending WP-31)
- **Target:** v0.3
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0039 introduced `AgentRegistry` and `GraphFactory` so agent behavior is declarative, but its own implementation state is explicit about what remains unbuilt: "v0 has exactly one graph shape (Tekos's retrieve/tool_call/reason/respond LangGraph workflow, `app/graph/build.py`), so there is no graph-shape selection to implement yet." Today `app/main.py` hardcodes a single route, `/v1/agents/tekos/chat`, calling a single compiled graph, `tekos_graph`; `GraphFactory` is a registry/config resolver, not a shape selector, and there is no dispatch keyed on `AgentDefinition`.

ADR-0326 sequences Arkos as the second real agent, and expects it to run on "the same shared platform" rather than a fork - but Arkos's workflow (long-form document generation, delegated Google Workspace, live Jira/Confluence) is not the same shape as Tekos's retrieve/tool/reason/respond loop. ADR-0202/0203 already generalize *what knowledge/tools* an agent may use; nothing yet generalizes *how the runtime executes a materially different workflow* for a second agent.

## Decision

Extend `GraphFactory` to select and build among multiple LangGraph workflow shapes, keyed off `AgentDefinition`/task declaration rather than a hardcoded route-to-graph mapping. Each graph shape is a distinct, named workflow module (mirroring `app/graph/build.py`'s existing structure); `GraphFactory` resolves which shape an agent's task requires, builds/caches it, and the runtime's HTTP layer becomes agent-name-driven rather than one hardcoded route per agent.

Arkos becomes the second graph shape and the first proof this mechanism works: a real OKF task bundle (not `agents/arkos/tasks/coming-soon.md`) exercising a workflow materially different from Tekos's. Both Tekos and Arkos declare `allowed_knowledge` including `knowledge.project` (ADR-0209) alongside their own domain-specific knowledge (`knowledge.tech` for both, in this first proof), demonstrating that knowledge-domain sharing (already decided by ADR-0202/0203) works identically regardless of which graph shape executes the task.

This ADR does not implement Comage, Advantage or Finage - ADR-0326 owns that full agent-by-agent sequencing; this ADR only proves the runtime mechanism generalizes past one hardcoded shape, using Arkos as the concrete second instance.

## Consequences

Adding a materially different agent workflow becomes a configuration-plus-new-graph-module change, not a fork of Agent Runtime's HTTP/registry layer. `app/main.py` grows a generic per-agent route resolved from `AgentRegistry` instead of one hardcoded path per agent.

## Security considerations

Graph-shape selection must not bypass `AgentRegistry`'s existing platform-ceiling enforcement (ADR-0039) - an agent cannot select a graph shape that grants it tools/knowledge beyond what its OKF declaration and platform policy already allow. Unknown/misconfigured graph-shape references fail startup loudly, consistent with `AgentRegistry`'s existing fail-fast behavior.

## Operational considerations

Startup validation must confirm every registered agent resolves to exactly one known graph shape. Tracing must record which graph shape served a given request, alongside the existing agent/task identifiers.

## Acceptance criteria

- `GraphFactory` builds/selects at least two distinct graph shapes (Tekos's existing one, plus Arkos's) from `AgentDefinition` alone, with no per-agent hardcoded route in `app/main.py` beyond generic dispatch.
- Arkos runs a real task end to end through its own graph shape.
- Tekos and Arkos both successfully retrieve `knowledge.project` content for the same `project_id` (ADR-0209's acceptance scenario), each through its own graph shape and its own task prompts/capabilities.
- Changing which graph shape an agent uses is a configuration/registration change, not a runtime code change to the other agent's path.
- Unit tests cover graph-shape resolution/selection; an end-to-end test exercises both Tekos's and Arkos's graphs against the same running Agent Runtime instance.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0005](0005-use-okf-v0-2-as-the-declarative-agent-definition-contract.md)
- [ADR-0006](0006-extend-okf-with-zuno-agent-specific-metadata.md)
- [ADR-0039](0039-make-agent-runtime-execute-the-okf-agent-contract.md)
- [ADR-0326](0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md)
- [ADR-0202](0202-introduce-logical-knowledge-domains.md)
- [ADR-0203](0203-enforce-knowledge-authorization-as-policy-intersection.md)
- [ADR-0209](0209-introduce-project-scoped-agent-memory.md)
