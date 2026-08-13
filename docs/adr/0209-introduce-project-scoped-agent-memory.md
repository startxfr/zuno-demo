# ADR-0209: Introduce project-scoped agent memory

- **Status:** To be implemented
- **Target:** v2
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team

## Context

Every Zuno agent conversation today is stateless server-side: `components/agent-bff` treats `session_id` as an opaque, unpersisted correlation string, and `components/agent-runtime`'s `AgentState` is an in-memory per-request object discarded after each turn. A user who tells Tekos, in one session, that a project runs OpenShift 4.22 across three AWS clusters and must keep C2 information local-only has to repeat that in every later session, and no other agent can ever see it.

ADR-0202 already introduces four logical knowledge domains (`knowledge.tech`, `knowledge.sales`, `knowledge.sxa-legacy`, `knowledge.adv`) as the stable, backend-hidden contract agents use to request knowledge, and ADR-0204 already establishes one dedicated PostgreSQL database per logical domain. None of the four cover per-engagement, cross-agent, cross-session project context - `knowledge.adv`'s `project_type` metadata field is a *business-domain* classification of Aramis-sourced ADV knowledge, not a per-engagement memory scope any agent can write to and read from. Separately, ADR-0034 already names "conversation memory" as a contributing input to effective-classification aggregation, and ADR-0039 names "memory policy" as something that should come from the OKF contract - both anticipate this decision without making it.

## Decision

Introduce a fifth logical knowledge domain, `knowledge.project`, following ADR-0202's existing contract exactly (chunks carry `domain`, `source`, `classification`, `acl_groups`, `provenance`, etc.), extended with a mandatory `project_id`. `knowledge.project` is explicitly distinct from `knowledge.adv`: the former is a caller-supplied per-engagement memory scope open to any agent, the latter is Aramis-sourced ADV business knowledge.

`project_id` becomes a first-class propagated context value, following the same header/context-propagation pattern ADR-0032/0033 already use for identity: BFF chat/session requests carry it (extends ADR-0054's OpenAPI contract with a new optional field), Agent Runtime forwards it on every RAG/memory/MCP call it makes on the caller's behalf.

Two persistence concerns are kept separate, per ADR-0204's per-domain dedicated-database pattern (a new `rag-project` binding, same precedent as `rag-tech`/`rag-sales`):

1. **Session/conversation history** - raw turns, stored for continuity/audit, not treated as durable knowledge and not retrieved as project memory by default.
2. **Durable project knowledge** - (a) structured project state (key facts, as rows/JSONB in PostgreSQL) and (b) semantic project memories (pgvector chunks under `knowledge.project`, reusing ADR-0202's common metadata contract). Both carry: `project_id`, author/user, agent, source/session, timestamp, classification, `acl_groups`, content, metadata - the full record shape required by this decision.

Conversation turns are never persisted into `knowledge.project` verbatim. An explicit **memory extraction step**, triggered at session end or an explicit checkpoint, identifies durable facts, decisions, constraints and actions from the conversation and writes only those into project state/memory. This step is itself subject to ADR-0035: if the conversation being summarized carries C2/C3 content, extraction runs against a local-only model, and extracted memories inherit the source classification rather than being silently downgraded.

Retrieval combines the current conversation context with `knowledge.project` and whatever other domains the active task authorizes (e.g. `knowledge.tech`), through the same knowledge router and fail-closed authorization intersection ADR-0202/ADR-0203 already define - multi-domain retrieval is already decided, not reinvented here.

**Project ACL**: a PostgreSQL project-membership table (`project_id` -> member subject/group) in the new project schema, checked at retrieval time via the same fail-closed `acl_groups` intersection ADR-0046 already implements for RAG chunks. This deliberately does not create a Keycloak group per project: the realm (`gitops/charts/keycloak/files/realm-zuno.json`) is fully static/GitOps-provisioned today, while projects are created ad hoc at runtime - membership is data, not identity infrastructure.

Retrieved project memory content feeds ADR-0034's effective-classification aggregation exactly like RAG documents and tool results do today, monotonic-escalation-only, never downgraded.

This ADR is the v2, project-isolated building block. ADR-0404 ("introduce controlled shared agent memory," v4, currently an unwritten placeholder) is left to define any later cross-project sharing/promotion; `knowledge.project` as decided here has no cross-project sharing.

## Consequences

Agents gain durable, cross-session, cross-agent memory scoped to an explicit engagement, without a parallel identity or profile store, and without weakening the classification/ACL guarantees the rest of the platform already relies on. Agent Runtime and BFF both gain a new propagated context field, and a new extraction step becomes part of the turn/session lifecycle.

## Security considerations

`knowledge.project` retrieval and writes are denied by default absent an explicit project-membership row - missing membership, missing classification metadata, or an unknown `project_id` must fail closed, the same posture ADR-0203/ADR-0046 already require for every other domain. Memory extraction must never raise the effective classification's visibility to a wider audience than the source conversation already had, and must never route C2/C3 conversation content to an external model to produce the summary.

## Operational considerations

Extraction failures must not silently drop a session's context; a failed extraction is logged and retried/flagged rather than treated as "nothing worth remembering." Project memory writes/retrievals are traceable with `project_id`, agent, task, user and domain, mirroring ADR-0203's existing knowledge-policy tracing requirement.

## Acceptance criteria

- With Tekos, a user states project `demo-001` facts (OpenShift 4.22, AWS, three clusters, C2 local-only); the session ends.
- A new session for `demo-001` lets Tekos retrieve these facts without the user repeating them.
- Arkos, in the same or a later session, retrieves the same permitted `demo-001` facts through the identical `knowledge.project` contract, with different task prompts/capabilities than Tekos.
- A user without `demo-001` project membership cannot retrieve any of its memories, structured state, or semantic chunks.
- Raw conversation turns are not persisted into `knowledge.project` unless they pass through the extraction step.
- Automated unit tests cover the extraction step's fact/decision identification and the project-membership fail-closed check; an end-to-end acceptance test exercises the full scenario above.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0006](0006-extend-okf-with-zuno-agent-specific-metadata.md)
- [ADR-0009](0009-separate-agent-runtime-from-ai-inference-gateway.md)
- [ADR-0032](0032-propagate-trusted-identity-end-to-end.md)
- [ADR-0033](0033-derive-user-identity-only-from-validated-tokens.md)
- [ADR-0034](0034-compute-effective-classification-from-the-complete-context.md)
- [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md)
- [ADR-0038](0038-use-standards-compliant-okf-v0-2-markdown-bundles.md)
- [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md)
- [ADR-0046](0046-make-rag-retrieval-metadata-aware-and-bilingual.md)
- [ADR-0054](0054-define-the-bff-contract-openapi-first.md)
- [ADR-0202](0202-introduce-logical-knowledge-domains.md)
- [ADR-0203](0203-enforce-knowledge-authorization-as-policy-intersection.md)
- [ADR-0204](0204-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md)
- [ADR-0326](0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md)
- [ADR-0404](0400-v4-roadmap.md#adr-0404-introduce-controlled-shared-agent-memory)
