---
okf_version: v0.2
type: task
title: Update opportunity status
zuno:
  allowed_tools:
    - salesforce.opportunity.update
  # ADR-0515: editable starters. Shown in the chat empty state, and in the
  # composer's slash menu (agent-frontend web/src/chat/TaskPromptMenu.tsx).
  # UX only - never parsed or enforced server-side, and picking one does NOT
  # select this task: the chat route always runs primary_task (ADR-0342).
  prompt_examples:
    - "Move the Startx renewal opportunity to Negotiation."
    - "Update the close date on this opportunity to the end of next month."
---

# Update opportunity status

Write a change (stage, amount, close date) to an existing Salesforce
opportunity via the live `salesforce.opportunity.update` capability.
ADR-0205: RAG/`knowledge.sales` stays write-free - a mutation always goes
through a live tool capability, never through indexed retrieval.

Declared for the OKF catalog (ADR-0038); no distinct Agent Runtime route
exists for it yet in v0 - the single `POST /v1/agents/comage/chat`
endpoint only executes `check-deal-status`. Wiring a dedicated route for
this task is v1 scope, matching Tekos's own `find-relevant-docs`/
`check-my-drive-docs` catalog-only tasks.
