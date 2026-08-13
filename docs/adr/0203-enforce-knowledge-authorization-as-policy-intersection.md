# ADR-0203: Enforce knowledge authorization as policy intersection

- **Status:** To be implemented
- **Target:** v2
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0011/ADR-0036 already define tool authorization as an intersection of agent, task, user role, classification and platform policy. RAG retrieval currently relies primarily on caller groups and chunk metadata, while the OKF task contract has `allowed_tools` but no symmetric task-level knowledge ceiling.

With several domains, an entitled agent must not automatically gain every RAG corpus available to the platform. A Comage task that needs Salesforce knowledge, for example, must not implicitly receive SXA legacy history unless that domain is explicitly declared and authorized.

## Decision

Extend the Zuno OKF task contract with `zuno.allowed_knowledge`, containing only logical knowledge-domain identifiers from ADR-0202.

Enforce knowledge access as a fail-closed intersection:

```text
allowed knowledge =
    agent knowledge declaration
  ∩ task allowed_knowledge
  ∩ user business-role rights
  ∩ document ACL/classification
  ∩ platform knowledge policy
```

An agent declaration is the ceiling formed by the knowledge domains declared across its approved OKF contract. A task may narrow that set but never widen it.

Introduce a GitOps-managed knowledge policy, analogous to `policies/tools/tool-policy.yaml`, mapping logical domains to allowed business roles, classification constraints and optional source/sub-domain restrictions. The policy references logical domains; physical backend endpoints belong to ADR-0204 bindings.

Agent entitlement (`agent_tekos`, `agent_comage`, ...) remains orthogonal per ADR-0040. Frontend visibility and agent entitlement do not imply knowledge-domain authorization.

## Consequences

RAG becomes as explicit and testable as MCP tool authorization. One shared Agent Runtime can safely serve tasks with different knowledge ceilings.

Task documents gain one additional declarative field and policy-negative tests must cover domain denial as well as chunk ACL denial.

## Security considerations

Missing task/domain declaration, unknown domain, missing user groups, missing policy entry or untrusted ACL/classification metadata must deny retrieval. A task cannot bypass the policy by calling a provider endpoint directly.

C2/C3 retrieved content still raises the effective turn classification under ADR-0034 and remains subject to external-model restrictions under ADR-0035.

## Operational considerations

Knowledge-policy decisions must be traceable with agent, task, user groups, domain, filters and denial reason. Traces must not contain sensitive document content solely to explain an authorization decision.

## Acceptance criteria

- An OKF task can declare `allowed_knowledge` independently from `allowed_tools`.
- A task that declares `knowledge.sales` cannot retrieve `knowledge.sxa-legacy` unless both the agent ceiling and platform/user policy also allow it.
- A user with agent entitlement but without the required business role is denied.
- A user with the business role but without agent entitlement remains denied by the existing BFF/agent boundary.
- ACL-restricted chunks remain invisible to callers whose groups do not intersect `acl_groups`.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md)
- [ADR-0034](0034-compute-effective-classification-from-the-complete-context.md)
- [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md)
- [ADR-0036](0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md)
- [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md)
- [ADR-0046](0046-make-rag-retrieval-metadata-aware-and-bilingual.md)
- [ADR-0202](0202-introduce-logical-knowledge-domains.md)
