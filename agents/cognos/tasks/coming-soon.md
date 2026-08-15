---
okf_version: v0.2
type: task
title: Coming soon
zuno:
  allowed_tools: []
---

# Coming soon

Cognos is not yet built. Planned scope (ADR-0349 §6): board-only
financial and strategic Q&A with a large RAG/MCP tool set that
explicitly excludes technical tools and the technical RAG corpora
(`knowledge.tech` never appears in a future Cognos task's
`allowed_knowledge`), gated on the `board` business role.

`allowed_tools` stays empty while `status: placeholder` (see
`agent.okf.md`) - a placeholder agent has zero tool-call capability by
construction (ADR-0036), matching it having no running Agent Runtime
workflow at all.
