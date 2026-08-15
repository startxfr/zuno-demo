---
okf_version: v0.2
type: task
title: Answer a technical question
zuno:
  allowed_tools:
    - search_confluence
    - web_search
  allowed_knowledge:
    - knowledge.tech
    - knowledge.project
---

# Answer a technical question

Answer a free-form technical question using the Tekos RAG corpus (official
OpenShift/Kubernetes/Keycloak/Ansible/Argo CD/Helm/Go documentation) plus
internal Confluence content first, falling back to a constrained web
search when the internal corpus has no grounded answer. Every answer
includes concise source citations.

This is the task the Agent Runtime's chat endpoint (`POST
/v1/agents/tekos/chat`) executes for every turn in v0 - see
`components/agent-runtime/app/registry.py` (ADR-0039) for how its
`allowed_tools` above and `prompts/answer-technical-question.md`'s system
prompt are resolved into the running LangGraph workflow.
