---
okf_version: v0.2
type: rag
title: Technical documentation retrieval
zuno:
  domain: knowledge.tech
  used_by_tasks:
    - answer-technical-question
    - find-relevant-docs
  freshness_expectation: semantic-read
  rationale: >-
    Tekos's core value is grounded technical Q&A: answer-technical-question
    retrieves from knowledge.tech first (falling back to web_search only
    when the internal corpus has no grounded answer, ADR-0205), and
    find-relevant-docs is a pure knowledge.tech lookup/browse task. No
    per-domain top_k override is needed today - both tasks use the
    agent-wide zuno.rag.top_k (5, see agent.okf.md).
---

# Technical documentation retrieval

Tekos's primary knowledge domain (ADR-0202): official product
documentation plus internal Confluence content. No retrieval tuning
diverges from the agent-wide default here, so this note is purely a
cross-reference back to the two tasks that declare it.

Documentary only - this file does not change what retrieve_node actually
requests (`agent.okf.md`'s `zuno.rag.top_k`) or what is authorized
(`tasks/*.md`'s `zuno.allowed_knowledge` intersected with
`policies/knowledge/knowledge-policy.yaml`). See `knowledge/tech/domain.yaml`
for the domain's own taxonomy and freshness objective.

**Known gap, noted rather than hidden:** `knowledge/tech/domain.yaml`'s
`technology_vocabulary` currently lists only `satellite`, `openshift`,
`openshift-ai`, `keycloak`, while Tekos's own `agent.okf.md`/README
describe its corpus as spanning OpenShift, Kubernetes, Keycloak, Ansible,
Argo CD, Helm and Go documentation. This note does not paper over that
mismatch with an invented `filters.technology` list - resolving it belongs
to whoever next edits `knowledge/tech/domain.yaml`'s vocabulary.
