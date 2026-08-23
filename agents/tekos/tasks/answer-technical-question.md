---
okf_version: v0.2
type: task
title: Answer a technical question
zuno:
  allowed_tools:
    - search_confluence
    - web_search
    - git.repository.read
    - git.repository.list
    # ADR-0516: a deliberate, narrow carve-out - Tekos gets diagram
    # generation (Mermaid-to-SVG, never leaves the cluster) for technical
    # questions that call for an architecture/sequence/relationship
    # diagram, but still never declares image.generation.create
    # (photorealistic/illustrative SDXL content stays Arkos/Comage's
    # job - see evaluations/tekos/security_checks.py's
    # tekos_chat_never_returns_photorealistic_images and gate_checks.py's
    # tekos_declares_no_dat_or_image_generation_capability, both updated
    # alongside this to assert exactly that boundary).
    - diagram.generation.create
  live_read_tool: search_confluence
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

ADR-0121: `git.repository.read`/`git.repository.list` add read-only
GitHub/GitLab repository access (`components/mcp-servers/git-forge`,
ADR-0120) alongside Confluence/web search - **public repositories only,
on either provider**. Tekos never declares the private-scoped
`git.repository.private.*` capabilities (GitLab private access, reserved
for Arkos) or any write/create capability.
