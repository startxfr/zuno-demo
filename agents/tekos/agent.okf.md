---
okf_version: v0.2
type: agent
title: Tekos
description: >-
  Technical consultant assistant. Answers technical questions grounded in
  official product documentation and internal Confluence content, with
  concise citations, and helps consultants locate relevant reference
  material across the RAG corpus and their own Drive.
provenance:
  maintainer: Zuno Demo architecture team
  repository: zuno-demo
verification:
  status: unverified
freshness:
  last_reviewed: "2026-08-05"
sources:
  - "technical-docs (RAG corpus: OpenShift/Kubernetes/Keycloak/Ansible/Argo CD/Helm/Go documentation)"
  - confluence
zuno:
  name: tekos
  status: active
  tasks:
    - answer-technical-question
    - find-relevant-docs
    - check-my-drive-docs
  rag:
    top_k: 5
  model:
    preferred_classification: C1
    notes: >-
      Public vendor/product documentation and general technical Q&A are C1
      (SaaS model use allowed). Answers that incorporate Confluence content
      must respect Confluence's C2 classification (policies/data-classification)
      for the portions of context drawn from it, even though the task's
      ceiling here is C1.
  access:
    # ADR-0040: agent entitlement group, orthogonal to the `consultant`
    # business role that governs tool/data permissions inside Tekos
    # (policies/tools/tool-policy.yaml).
    groups:
      - agent_tekos
  ui:
    displayName: Tekos
    tileDescription: Technical Q&A with citations, for consultants.
    color: "#0066CC"
    icon: code
---

# Tekos

Technical consultant assistant. Tekos is the only agent with `status:
active` for v0 (MEMORY.md section 9, docs/agents/tekos.md): it is the
first vertical slice and validates frontend, BFF, Keycloak, runtime, AI
gateway, RAG, MCP Confluence, model routing, streaming and citations end
to end.

Conforms to `platform/okf/schema/zuno-okf-v0.2.schema.json` (ADR-0005,
ADR-0006, ADR-0038). Task detail lives in `tasks/*.md`, linked by name from
`zuno.tasks` above; the system prompt for the primary task lives in
`prompts/answer-technical-question.md`.
