# ADR-0333: Introduce logical knowledge domains

- **Status:** To be implemented
- **Target:** v1
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team

## Context

Zuno currently has a mature technical RAG path, but the agent contract still tends to describe RAG as a corpus/collection attached to an agent. The target platform now needs several independently governed bodies of knowledge:

- technical product knowledge from official web documentation and internal Confluence;
- current sales knowledge asynchronously ingested from Salesforce;
- historical SXA schema/data imported from a legacy SQL dump;
- ADV/project knowledge asynchronously ingested from Aramis.

If agents refer directly to a PostgreSQL database, vector collection, service hostname or vendor-specific RAG backend, agent definitions become coupled to deployment choices. Conversely, introducing a separate AI-profile/capability catalogue would duplicate the existing OKF + Keycloak + policy model.

## Decision

Introduce four stable **logical knowledge-domain identifiers**:

- `knowledge.tech`
- `knowledge.sales`
- `knowledge.sxa-legacy`
- `knowledge.adv`

The logical domain is the contract exposed to agents/tasks. It describes what knowledge is being requested, not how or where that knowledge is stored.

Add a declarative `knowledge/` area in the repository containing one domain descriptor per logical domain. Domain descriptors may declare taxonomy, source classes, freshness objectives, classification defaults and policy references, but **must not contain physical database names, service endpoints, secrets or credentials**.

OKF remains the capability catalogue for agents. Agent/task bundles reference logical knowledge domains; no parallel `AIProfile`, `CapabilityBundle` or separate persona configuration is introduced. Keycloak remains the source of identity/business roles and platform policies remain the authorization ceiling.

### Domain taxonomy

All chunks keep common metadata:

- `domain`
- `source`
- `source_type`
- `language`
- `classification`
- `acl_groups`
- `provenance`
- `source_modified_at`
- `indexed_at`
- `stale_after`

Domain-specific metadata extends this common contract:

- `knowledge.tech`: `technology` (canonical cross-source key), `product`, `version`, optional `skill_scope` (`architecture`, `build`, `run`, ...);
- `knowledge.sales`: `deal_type` (`architecture`, `build`, `run`, `training`, `staffing`, `market`, `mixed`), customer/opportunity/business-unit/status/year metadata;
- `knowledge.sxa-legacy`: schema/table/column/relationship/record-type/date/customer/project metadata;
- `knowledge.adv`: `project_type`, project/customer/status/owner/business-unit/date metadata.

For `knowledge.tech`, official web documentation and Confluence **must use the same canonical `technology` vocabulary** so queries can combine internal and official content without knowing the source implementation.

## Consequences

Agents become portable across vector stores, RAG providers and namespace/database changes. New knowledge domains can be introduced without forking Agent Runtime.

The platform gains an explicit distinction between **DataSource** (for example Confluence or Salesforce) and **KnowledgeDomain** (for example `knowledge.tech` or `knowledge.sales`). The same source may support both an indexed knowledge path and a live tool path.

## Security considerations

A logical domain does not grant access. Authorization is defined separately by ADR-0334 and document-level ACL/classification remains mandatory. Sensitive sources must fail closed when ACL/classification metadata is missing.

## Operational considerations

Each retrieved item must expose domain/source/provenance/freshness metadata in traces and citations so operators can explain which domain and source produced an answer.

## Acceptance criteria

- Agent/task definitions can reference `knowledge.tech`, `knowledge.sales`, `knowledge.sxa-legacy` and `knowledge.adv` without physical endpoint/database identifiers.
- A technical query can filter one canonical `technology` across both official web and Confluence chunks.
- Repository validation rejects an unknown logical knowledge-domain reference.
- No new user/persona profile store duplicates Keycloak business roles or OKF capability declarations.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0005](0005-use-okf-v0-2-as-the-declarative-agent-definition-contract.md)
- [ADR-0038](0038-use-standards-compliant-okf-v0-2-markdown-bundles.md)
- [ADR-0039](0039-make-agent-runtime-execute-the-okf-agent-contract.md)
- [ADR-0046](0046-make-rag-retrieval-metadata-aware-and-bilingual.md)
- [ADR-0330](0330-integrate-the-rag-ingestion-pipeline-as-a-day1-component.md)
- [ADR-0334](0334-enforce-knowledge-authorization-as-policy-intersection.md)
- [ADR-0338](0338-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md)
