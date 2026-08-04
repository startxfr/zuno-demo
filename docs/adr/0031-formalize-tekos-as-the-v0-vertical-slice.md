# ADR-0031: Formalize Tekos as the v0 vertical slice

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The repository currently describes five agents as the platform catalog, but only Tekos has an active implementation path. The current `agents/tekos/agent.okf.yaml`, `components/agent-runtime`, evaluation harness, frontend/BFF, RAG and MCP Confluence work form the first complete vertical slice. Leaving this scope implicit creates a mismatch between the repository-level product promise and the executable MVP.

## Decision

Define v0 as a Tekos-first vertical slice. The other four agents remain part of the catalog and architecture contract, but their full business implementations move to v1. v0 must prove the generic platform path end to end: authenticated frontend, BFF, Agent Runtime, RAG, MCP, model routing, streaming, citations, evaluation and policy enforcement.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

The v0 milestone becomes achievable and testable within the stated MVP constraint. Documentation must distinguish catalog presence from functional readiness. v1 becomes the release that makes all five initial agents business-functional.

## Security considerations

No security control may be deferred merely because an agent is catalog-only. Shared platform boundaries must already assume future agents with different data classifications.

## Operational considerations

Update release documentation and acceptance gates so Tekos is the only mandatory end-to-end business path in v0 while the other agent definitions remain structurally valid.

## Implementation state

**Implemented (2026-08-05).** `README.md`'s "v0 build status" and
`MEMORY.md` section 15 now state explicitly that Tekos is the only
mandatory end-to-end business path for v0, with Comage/Advantage/Finage/
Arkos as catalog-only (OKF definition + reserved namespace + access-gated
portal tile, no running workflow, business-functional build moved to v1).
Per the Security considerations above ("no security control may be
deferred merely because an agent is catalog-only"), `ansible/roles/agents/
tasks/check.yml` (`make check`) now structurally validates the four
catalog-only agents' `agent.okf.yaml` files (apiVersion, kind,
`metadata.status: placeholder`) rather than leaving them entirely
unchecked - see `ansible/roles/agents/README.md`.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0007
- ADR-0008
- ADR-0027
- ADR-0028

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
