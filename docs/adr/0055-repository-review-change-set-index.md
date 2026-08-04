# ADR-0055: Repository review change-set index

- **Status:** To be implemented
- **Target:** v0/v1
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The 2026-08-05 repository review identified a coherent set of architectural corrections and evolutions. This index groups the new ADRs without modifying the existing `docs/adr/README.md`, so the archive can be overlaid safely on the project and the main ADR index can be updated during integration.

## Decision

Track the following review decisions as independent ADRs, all initially in `To be implemented` state.

| ADR | Target | Status | Decision |
|---|---|---|---|
| [ADR-0031](0031-formalize-tekos-as-the-v0-vertical-slice.md) | v0 | To be implemented | Formalize Tekos as the v0 vertical slice |
| [ADR-0032](0032-propagate-trusted-identity-end-to-end.md) | v0 | To be implemented | Propagate trusted identity end to end |
| [ADR-0033](0033-derive-user-identity-only-from-validated-tokens.md) | v0 | To be implemented | Derive user identity only from validated tokens |
| [ADR-0034](0034-compute-effective-classification-from-the-complete-context.md) | v0 | To be implemented | Compute effective classification from the complete context |
| [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md) | v0 | To be implemented | Prevent restricted internal context from reaching external models |
| [ADR-0036](0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md) | v0 | To be implemented | Enforce the complete MCP authorization intersection in the gateway |
| [ADR-0037](0037-protect-mcp-servers-with-network-and-workload-identity-boundaries.md) | v0 | To be implemented | Protect MCP servers with network and workload identity boundaries |
| [ADR-0038](0038-use-standards-compliant-okf-v0-2-markdown-bundles.md) | v0 | To be implemented | Use standards-compliant OKF v0.2 Markdown bundles |
| [ADR-0039](0039-make-agent-runtime-execute-the-okf-agent-contract.md) | v0 | To be implemented | Make Agent Runtime execute the OKF agent contract |
| [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md) | v0 | To be implemented | Separate agent entitlement from business role authorization |
| [ADR-0041](0041-remove-nominative-demo-identities-and-static-passwords-from-git.md) | v0 | To be implemented | Remove nominative demo identities and static passwords from Git |
| [ADR-0042](0042-use-opaque-browser-sessions-with-server-side-token-storage.md) | v1 | To be implemented | Use opaque browser sessions with server-side token storage |
| [ADR-0043](0043-use-standard-mcp-protocol-behind-the-zuno-mcp-gateway.md) | v1 | To be implemented | Use standard MCP protocol behind the Zuno MCP Gateway |
| [ADR-0044](0044-use-patternfly-react-for-the-agent-frontend.md) | v0 | To be implemented | Use PatternFly React for the agent frontend |
| [ADR-0045](0045-stream-responses-end-to-end-with-sse.md) | v0 | To be implemented | Stream responses end to end with SSE |
| [ADR-0046](0046-make-rag-retrieval-metadata-aware-and-bilingual.md) | v0 | To be implemented | Make RAG retrieval metadata-aware and bilingual |
| [ADR-0047](0047-manage-the-complete-openshift-ai-prerequisite-lifecycle.md) | v0 | To be implemented | Manage the complete OpenShift AI prerequisite lifecycle |
| [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md) | v0 | To be implemented | Discover supported operator channels and serving runtimes at deployment time |
| [ADR-0049](0049-use-zuno-as-a-policy-router-in-front-of-openshift-ai-maas.md) | v1 | To be implemented | Use Zuno as a policy router in front of OpenShift AI MaaS |
| [ADR-0050](0050-abstract-the-rag-backend-and-integrate-openshift-ai-ogx.md) | v1 | To be implemented | Abstract the RAG backend and integrate OpenShift AI OGX |
| [ADR-0051](0051-use-immutable-and-verifiable-software-supply-chain-artifacts.md) | v0 | To be implemented | Use immutable and verifiable software supply chain artifacts |
| [ADR-0052](0052-harden-all-workloads-for-openshift-restricted-security-and-secnumcloud-objectives.md) | v0 | To be implemented | Harden all workloads for OpenShift restricted security and SecNumCloud objectives |
| [ADR-0053](0053-make-make-check-an-end-to-end-acceptance-and-security-gate.md) | v0 | To be implemented | Make make check an end-to-end acceptance and security gate |
| [ADR-0054](0054-define-the-bff-contract-openapi-first.md) | v0 | To be implemented | Define the BFF contract OpenAPI-first |

## Alternatives considered

A single monolithic review ADR was rejected because identity, data classification, OKF, MaaS, RAG, frontend, supply chain and operational validation have independent implementation and rollback lifecycles.

## Consequences

The project can implement and close each change independently while preserving a single review baseline.

## Security considerations

Security-critical ADRs must be implemented before expanding the platform to additional business agents that access C2/C3 data.

## Operational considerations

When this change set is integrated, add ADR-0031 through ADR-0055 to `docs/adr/README.md` and keep each status synchronized with actual implementation evidence.

## Implementation state

To be implemented. This file is an integration index only.

## Related ADRs

See each ADR listed above and the existing [ADR index](README.md).
