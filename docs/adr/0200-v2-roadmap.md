# v2 roadmap decisions (ADR-0201 – ADR-0210)

- **Status:** Proposed
- **Target:** v2
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team

v2 matures the single-agent (Tekos) pattern: MCP and RAG maturity, and sovereign/SaaS model routing, all behind the same trusted policy boundaries v0/v1 already established. It does not add a second agent - that is v3 (see [ADR-0326](0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md)) - and it does not add agent-to-agent delegation - that is v4 (see [0400-v4-roadmap.md](0400-v4-roadmap.md)).

Each of the 10 decisions below was promoted to its own full decision record as the design matured; only the Decision line is unique per entry - [Standard clauses](README.md#standard-clauses) (Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution, Related ADRs) apply to every entry unless overridden here.

### ADR-0201: Complete the OpenShift AI MaaS governance plane integration

Promoted to a full decision record: see [ADR-0201](0201-complete-the-openshift-ai-maas-governance-plane-integration.md) (sovereign/SaaS model access and consumption governance in front of Zuno's policy router).

### ADR-0202: Introduce logical knowledge domains

Promoted to a full decision record: see [ADR-0202](0202-introduce-logical-knowledge-domains.md).

### ADR-0203: Enforce knowledge authorization as policy intersection

Promoted to a full decision record: see [ADR-0203](0203-enforce-knowledge-authorization-as-policy-intersection.md).

### ADR-0204: Generalize the RAG platform to multiple isolated knowledge domains

Promoted to a full decision record: see [ADR-0204](0204-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md).

### ADR-0205: Prefer indexed knowledge for read and live tools for freshness and write

Promoted to a full decision record: see [ADR-0205](0205-prefer-indexed-knowledge-for-read-and-live-tools-for-freshness-and-write.md).

### ADR-0206: Separate current Salesforce knowledge from legacy SXA

Promoted to a full decision record: see [ADR-0206](0206-separate-current-salesforce-knowledge-from-legacy-sxa.md).

### ADR-0207: Decouple logical tool capabilities from physical backend bindings

Promoted to a full decision record: see [ADR-0207](0207-decouple-logical-tool-capabilities-from-physical-backend-bindings.md).

### ADR-0208: Standardize enterprise tool authentication and delegation

Promoted to a full decision record: see [ADR-0208](0208-standardize-enterprise-tool-authentication-and-delegation.md).

### ADR-0209: Introduce project-scoped agent memory

Promoted to a full decision record: see [ADR-0209](0209-introduce-project-scoped-agent-memory.md).

### ADR-0210: Implement Confluence as the first real external MCP integration

Promoted to a full decision record: see [ADR-0210](0210-implement-confluence-as-the-first-real-external-mcp-integration.md) (Tekos's first live, real-backend MCP tool alongside its indexed RAG path).
