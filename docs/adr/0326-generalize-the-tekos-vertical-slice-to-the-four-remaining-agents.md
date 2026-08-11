# ADR-0326: Generalize the Tekos vertical slice to the four remaining agents

- **Status:** To be implemented
- **Target:** v1
- **Date:** 2026-08-11
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0031 deliberately made Tekos the only mandatory end-to-end v0 vertical slice while Arkos, Comage, Advantage and Finage remained declarative placeholders. This reduced v0 scope and allowed the shared platform path to mature first.

The platform now has reusable frontend/BFF, Agent Runtime, AI Gateway, RAG, MCP Gateway, identity, OKF execution, policy enforcement, observability and Day 0/Day 1 deployment patterns. The next architectural proof is no longer another shared component: it is demonstrating that a second, third and fourth business domain can be implemented **without forking the shared runtime architecture**.

The four remaining agents exercise complementary integration risks:

- **Arkos:** technical knowledge, Google Drive/Docs write access, long-form document generation and higher-reasoning model selection;
- **Comage:** sales-data MCP plus delegated Gmail access and user-specific follow-up reasoning;
- **Advantage:** restricted sales-data views beginning at `BDCC recu` / downstream business states;
- **Finage:** the narrowest finance-oriented sales-data view beginning at `A facturer` / invoiced states.

## Decision

Implement the four remaining agents in v1 as **declarative instances of the same shared platform**, not as independent application forks.

All agent-specific behavior must remain under each agent's OKF bundle, policies, prompts, RAG references, tool bindings, tests and deployment parameters. Changes to shared Python/Go services are allowed only when they implement a reusable platform capability required by more than one agent or a formally accepted generic extension.

### Recommended implementation sequence

1. **Arkos as the second vertical slice.** It proves a materially different workflow: Drive/Docs delegated access, structured long-form document generation, advanced model-routing/cost policy and reuse of technical knowledge. In v1 it may reuse the same technical RAG collections as Tekos; direct agent-to-agent delegation remains governed by the v2 A2A roadmap (ADR-0201/ADR-0202) unless that roadmap is separately changed.
2. **Comage as the third vertical slice.** It proves per-user Gmail delegation combined with shared commercial PostgreSQL/MCP data and multiple recurring sales tasks.
3. **Advantage and Finage after the sales-data authorization boundary is proven.** They reuse the commercial MCP implementation but must expose deliberately narrower server-side query capabilities according to business state, role and task. Their restricted views must not rely on prompt instructions or client-side filtering.

### Mandatory common completion pattern

Each agent becomes `active` only when it has:

- real OKF task bundles replacing `coming-soon`;
- one dedicated frontend and one BFF deployment per ADR-0008;
- Keycloak agent entitlement plus business-role authorization;
- required RAG/MCP bindings;
- OpenAPI-covered BFF behavior and SSE streaming where applicable;
- twenty acceptance scenarios and the ADR-0028 quality threshold;
- C1/C2/C3 and external-model eligibility tests;
- tracing/usage instrumentation;
- Day 1 install/check/uninstall coverage.

## Consequences

v1 becomes the release that proves Zuno is a platform rather than a Tekos-specific implementation. Shared-runtime defects will surface earlier because the agents exercise different identity, tool, data and model-routing paths.

The sequence intentionally delays Advantage/Finage until the commercial-data boundary is robust enough to prove least privilege using server-side tools/query contracts.

## Security considerations

Agent expansion must not widen the generic platform permissions.

- Google delegated tokens for Arkos/Comage remain user-scoped and server-side.
- Advantage and Finage get different MCP tool/query capabilities despite sharing the same PostgreSQL platform.
- Business-state filtering is enforced in controlled MCP/database operations, never only in prompts.
- Every agent keeps separate entitlement groups and namespaces.
- C2/C3 context remains subject to ADR-0035 externalization restrictions.

## Operational considerations

The acceptance pipeline should expose readiness independently per agent. A failure in an optional v1 agent must be diagnosable without hiding the health of the shared runtime.

Evaluation fixtures must use synthetic/anonymized commercial and document data appropriate for the public repository.

## Acceptance criteria

- Arkos, Comage, Advantage and Finage move from `status: placeholder` to active only after their complete common acceptance pattern passes.
- No agent introduces a private fork of Agent Runtime, AI Gateway or MCP Gateway.
- Arkos proves delegated Drive/Docs access and long-form document workflow.
- Comage proves delegated Gmail plus sales-data MCP use.
- Advantage cannot retrieve sales records outside its permitted business-state window.
- Finage cannot retrieve records before the `A facturer`/invoicing boundary.
- All five agents meet the evaluation/security gates required by existing ADRs.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0007](0007-separate-agent-instances-from-reusable-platform-components.md)
- [ADR-0008](0008-use-one-frontend-and-one-bff-deployment-per-agent.md)
- [ADR-0014](0014-use-delegated-google-oauth-for-google-workspace-access.md)
- [ADR-0017](0017-access-sales-data-through-controlled-mcp-tools.md)
- [ADR-0027](0027-evaluate-every-agent-with-twenty-acceptance-scenarios.md)
- [ADR-0028](0028-require-a-seventy-five-percent-evaluation-threshold.md)
- [ADR-0031](0031-formalize-tekos-as-the-v0-vertical-slice.md)
- [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md)
- [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md)
- [ADR-0201](0200-v2-roadmap.md#adr-0201-introduce-agent-to-agent-communication)
- [ADR-0202](0200-v2-roadmap.md#adr-0202-adopt-a2a-as-the-inter-agent-protocol)
