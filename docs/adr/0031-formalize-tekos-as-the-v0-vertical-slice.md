# ADR-0031: Formalize Tekos as the v0 vertical slice

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The repository currently describes five agents as the platform catalog, but only Tekos has an active implementation path. The current `agents/tekos/agent.okf.yaml`, `components/agent-runtime`, evaluation harness, frontend/BFF, RAG and MCP Confluence work form the first complete vertical slice. Leaving this scope implicit creates a mismatch between the repository-level product promise and the executable MVP.

## Decision

Define v0 as a Tekos-first vertical slice. The other four agents remain part of the catalog and architecture contract, but their full business implementations move to v1. v0 must prove the generic platform path end to end: authenticated frontend, BFF, Agent Runtime, RAG, MCP, model routing, streaming, citations, evaluation and policy enforcement.

## Consequences

The v0 milestone becomes achievable and testable within the stated MVP constraint. Documentation must distinguish catalog presence from functional readiness. v1 becomes the release that makes all five initial agents business-functional.

## Security considerations

No security control may be deferred merely because an agent is catalog-only. Shared platform boundaries must already assume future agents with different data classifications.

## Operational considerations

Update release documentation and acceptance gates so Tekos is the only mandatory end-to-end business path in v0 while the other agent definitions remain structurally valid.

## Implementation state

**Implemented (2026-08-05).**

- `README.md`'s "v0 build status" and `MEMORY.md` section 15 state that Tekos is the only mandatory end-to-end business path for v0; Comage/Advantage/Finage/Arkos are catalog-only (OKF definition + reserved namespace + access-gated portal tile, no running workflow).
- `ansible/roles/agents/tasks/check.yml` (`make check`) structurally validates the four catalog-only agents' `agent.okf.yaml` files (apiVersion, kind, `metadata.status: placeholder`) rather than leaving them unchecked (per the Security considerations above).

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0007](0007-separate-agent-instances-from-reusable-platform-components.md)
- [ADR-0008](0008-use-one-frontend-and-one-bff-deployment-per-agent.md)
- [ADR-0027](0027-evaluate-every-agent-with-twenty-acceptance-scenarios.md)
- [ADR-0028](0028-require-a-seventy-five-percent-evaluation-threshold.md)
