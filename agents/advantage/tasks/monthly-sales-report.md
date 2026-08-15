---
okf_version: v0.2
type: task
title: Produce the monthly in-progress sales report
zuno:
  allowed_tools: []
  allowed_knowledge:
    - knowledge.adv
---

# Produce the monthly in-progress sales report

Produce the monthly in-progress sales administration report (margin by
state/customer/technology, MEMORY.md section 9), drawing on
`knowledge.adv` project/delivery state.

Declared for the OKF catalog (ADR-0038); no distinct Agent Runtime route
exists for it yet in v0 - the single `POST /v1/agents/advantage/chat`
endpoint only executes `answer-project-question`. Text/table + PDF report
generation is v1 scope, not built here.
