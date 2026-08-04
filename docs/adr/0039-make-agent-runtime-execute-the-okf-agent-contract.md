# ADR-0039: Make Agent Runtime execute the OKF agent contract

- **Status:** To be implemented
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

This ADR records an agreed architectural change identified during the 2026-08-05 repository review. **No implementation is claimed by this ADR.** The status remains `To be implemented` until code, GitOps, documentation and acceptance tests prove the decision is in effect.

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
