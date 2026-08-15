# ADR-0326: Generalize the Tekos vertical slice to the four remaining agents

- **Status:** Partially implemented (Arkos and Comage slices merged, 2 of 4; both cluster gates pending)
- **Target:** v0.3
- **Date:** 2026-08-11
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0031 deliberately made Tekos the only mandatory end-to-end v0 vertical slice while Arkos, Comage, Advantage and Finage remained declarative placeholders. This reduced v0 scope and allowed the shared platform path to mature first.

The platform now has reusable frontend/BFF, Agent Runtime, AI Gateway, RAG, MCP Gateway, identity, OKF execution, policy enforcement, observability and Day 0/Day 1 deployment patterns. The next architectural proof is no longer another shared component: it is demonstrating that a second, third and fourth business domain can be implemented **without forking the shared runtime architecture**.

The four remaining agents exercise complementary integration risks and now consume logical capabilities rather than physical RAG/MCP endpoints:

- **Arkos:** `knowledge.tech`, live Confluence/Jira capabilities where needed, delegated Google Drive/Docs write access, long-form document generation and higher-reasoning model selection;
- **Comage:** `knowledge.sales` as the preferred commercial read path, `knowledge.sxa-legacy` for historical SXA lookup, live Salesforce MCP for freshness-sensitive reads and all writes, plus delegated Google Workspace capabilities;
- **Advantage:** `knowledge.adv` asynchronously ingested from Aramis, with any cross-domain commercial access explicitly declared and policy-controlled rather than inherited from Comage;
- **Finage:** finance-scoped knowledge/tool access declared explicitly, using the same shared capability model without inheriting broad sales or ADV permissions.

## Decision

Implement the four remaining agents in v0.1 as **declarative instances of the same shared platform**, not as independent application forks.

All agent-specific behavior must remain under each agent's OKF bundle, policies, prompts, **logical knowledge-domain references**, logical tool capabilities, tests and deployment parameters. Physical RAG databases, MCP server endpoints and API credentials are platform bindings and must not be embedded in agent definitions. Changes to shared Python/Go services are allowed only when they implement a reusable platform capability required by more than one agent or a formally accepted generic extension.

### Recommended implementation sequence

1. **Arkos as the second vertical slice.** It proves a materially different workflow: delegated Drive/Docs access, live Jira/Confluence actions where authorized, structured long-form document generation, advanced model-routing/cost policy and reuse of `knowledge.tech`. Direct agent-to-agent delegation remains governed by the v0.4 A2A roadmap (ADR-0401/ADR-0402) unless that roadmap is separately changed.
2. **Comage as the third vertical slice.** It proves the indexed-read/live-action pattern: semantic reads prefer `knowledge.sales`, freshness-sensitive reads and writes use Salesforce MCP, historical questions may use `knowledge.sxa-legacy`, and personal Google Workspace actions preserve delegated user identity.
3. **Advantage and Finage after the cross-domain authorization boundary is proven.** Advantage proves the independent `knowledge.adv` domain backed by Aramis. Finage proves that a role can receive only finance-appropriate domain/tool capabilities. Neither restricted view may rely on prompt instructions or client-side filtering.

### Mandatory common completion pattern

Each agent becomes `active` only when it has:

- real OKF task bundles replacing `coming-soon`;
- one dedicated frontend and one BFF deployment per ADR-0008;
- Keycloak agent entitlement plus business-role authorization;
- required logical `allowed_knowledge` and `allowed_tools` declarations plus platform bindings;
- OpenAPI-covered BFF behavior and SSE streaming where applicable;
- twenty acceptance scenarios and the ADR-0028 quality threshold;
- C1/C2/C3 and external-model eligibility tests;
- tracing/usage instrumentation;
- Day 1 install/check/uninstall coverage.

## Consequences

v0.1 becomes the release that proves Zuno is a platform rather than a Tekos-specific implementation. Shared-runtime defects will surface earlier because the agents exercise different identity, tool, data and model-routing paths.

The sequence intentionally delays Advantage/Finage until the commercial-data boundary is robust enough to prove least privilege using server-side tools/query contracts.

## Security considerations

Agent expansion must not widen the generic platform permissions.

- Google delegated tokens for Arkos/Comage remain user-scoped and server-side.
- Advantage and Finage get different knowledge/tool capabilities even when physical PostgreSQL or MCP runtimes are shared.
- Source/domain filters and business-state restrictions are enforced by knowledge/tool policy and controlled backend operations, never only in prompts.
- Every agent keeps a separate entitlement boundary; workloads may share `zuno-ai-run` per ADR-0329, with authorization and workload identity providing isolation rather than per-agent namespaces.
- C2/C3 context remains subject to ADR-0035 externalization restrictions.

## Operational considerations

The acceptance pipeline should expose readiness independently per agent. A failure in an optional v0.1 agent must be diagnosable without hiding the health of the shared runtime.

Evaluation fixtures must use synthetic/anonymized commercial and document data appropriate for the public repository.

## Acceptance criteria

- Arkos, Comage, Advantage and Finage move from `status: placeholder` to active only after their complete common acceptance pattern passes.
- No agent introduces a private fork of Agent Runtime, AI Gateway or MCP Gateway.
- Arkos proves delegated Drive/Docs access, `knowledge.tech` reuse and live Jira/Confluence actions without physical endpoint coupling.
- Comage proves `knowledge.sales` preferred reads, live Salesforce freshness/write actions, delegated Google Workspace access and explicit legacy SXA access.
- Advantage proves `knowledge.adv` from Aramis and cannot inherit broader Comage/Sales capabilities implicitly.
- Finage proves finance-scoped knowledge/tool access without inheriting broad Sales/ADV access.
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
- [ADR-0202](0202-introduce-logical-knowledge-domains.md)
- [ADR-0203](0203-enforce-knowledge-authorization-as-policy-intersection.md)
- [ADR-0204](0204-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md)
- [ADR-0205](0205-prefer-indexed-knowledge-for-read-and-live-tools-for-freshness-and-write.md)
- [ADR-0206](0206-separate-current-salesforce-knowledge-from-legacy-sxa.md)
- [ADR-0116](0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md)
- [ADR-0208](0208-standardize-enterprise-tool-authentication-and-delegation.md)
- [ADR-0340](0340-extend-business-role-authorization-with-cdp-and-scoped-capabilities.md)
- [ADR-0401](0400-v0.4-roadmap.md#adr-0401-introduce-agent-to-agent-communication)
- [ADR-0402](0400-v0.4-roadmap.md#adr-0402-adopt-a2a-as-the-inter-agent-protocol)
