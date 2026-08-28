---
okf_version: v0.2
type: task
title: Check my Drive and mail
zuno:
  allowed_tools:
    - list_drive_files
    - read_gmail
  # ADR-0515: editable starters. Shown in the chat empty state, and in the
  # composer's slash menu (agent-frontend web/src/chat/TaskPromptMenu.tsx).
  # UX only - never parsed or enforced server-side, and picking one does NOT
  # select this task: the chat route always runs primary_task (ADR-0342).
  prompt_examples:
    - "List my Drive documents and emails about this customer's invoices."
    - "Which emails mention an unpaid invoice for this account?"
---

# Check my Drive and mail

List the authenticated finance user's own Google Drive documents and
Gmail messages relevant to a given account or invoice, using delegated
end-user OAuth2 (ADR-0014, `auth_mode: delegated-user`) so only content
the user can already see is returned - the same delegated Google
Workspace pattern Arkos/Comage/Advantage proved, exercised here under
Finage's own `finance` role.

Declared for the OKF catalog (ADR-0038); no distinct Agent Runtime route
exists for it yet in v0 - the single `POST /v1/agents/finage/chat`
endpoint only executes `answer-finance-question`. Wiring a dedicated
route for this task is v1 scope.
