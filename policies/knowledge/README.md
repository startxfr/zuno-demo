# Knowledge policy (ADR-0203)

`knowledge-policy.yaml` is the platform-policy layer of the ADR-0203
knowledge-authorization intersection: it maps each logical knowledge domain
(`knowledge/<domain>/domain.yaml`, ADR-0202) to the Keycloak business-role
groups permitted to retrieve from it.

Rules:

- This file references logical domains only. Physical backend endpoints
  belong to `platform/bindings/knowledge/bindings.yaml` (ADR-0204, WP-21).
- An agent's knowledge ceiling is the union of every task's own
  `zuno.allowed_knowledge` (mirroring how the tool ceiling works - see
  `platform/bindings/tools/README.md`) - a task narrows, never widens it.
- Missing task declaration, unknown domain, missing user groups or a
  missing policy entry all deny retrieval (fail closed). Document-level
  ACL/classification metadata is enforced independently by
  `components/rag-service/app/search.py`'s existing filter - this file only
  gates domain-level access.
- Consumed by `components/agent-runtime/app/knowledge.py`
  (`KnowledgePolicyStore` + `evaluate_knowledge()`), called from
  `app/graph/nodes.py:retrieve_node` before every RAG search.

The file ships inside the agent-runtime image (repo-root build context, see
`components/agent-runtime/Dockerfile`).
