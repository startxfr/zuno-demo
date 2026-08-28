---
okf_version: v0.2
type: task
title: Produce the monthly in-progress sales report
zuno:
  allowed_tools: []
  allowed_knowledge:
    - knowledge.adv
  # ADR-0515: editable starters. Shown in the chat empty state, and in the
  # composer's slash menu (agent-frontend web/src/chat/TaskPromptMenu.tsx).
  # UX only - never parsed or enforced server-side, and picking one does NOT
  # select this task: the chat route always runs primary_task (ADR-0342).
  prompt_examples:
    - "Produce the monthly in-progress sales report."
    - "Break down margin by customer and technology for this month."
---

# Produce the monthly in-progress sales report

Produce the monthly in-progress sales administration report (margin by
state/customer/technology, MEMORY.md section 9), drawing on
`knowledge.adv` project/delivery state.

Declared for the OKF catalog (ADR-0038); no distinct Agent Runtime route
exists for it yet in v0 - the single `POST /v1/agents/advantage/chat`
endpoint only executes `answer-project-question`. Text/table + PDF report
generation is v1 scope, not built here.
