---
okf_version: v0.2
type: task
title: Identify new business with a client PO received
zuno:
  allowed_tools: []
  allowed_knowledge:
    - knowledge.adv
---

# Identify new business with a client PO received

Surface new business whose client purchase order has been received in
the last rolling window (MEMORY.md section 9: 3 rolling days), drawing on
`knowledge.adv` project/delivery state.

Declared for the OKF catalog (ADR-0038); no distinct Agent Runtime route
exists for it yet in v0 - the single `POST /v1/agents/advantage/chat`
endpoint only executes `answer-project-question`. A deterministic
structured-query capability - an exact PO-received-date filter, not
something a RAG chunk should approximate - is v1 scope, not built here. It
would have to be built against a live source: the comparable legacy SXA
aggregation capability was removed by ADR-0219, since a closed pre-2021
record has nothing for such a tool to be authoritative about.
