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
    - "List my Drive documents and emails about the Startx account."
    - "Which recent emails mention the renewal negotiation?"
---

# Check my Drive and mail

List the authenticated sales rep's own Google Drive documents and Gmail
messages relevant to a given account or opportunity, using delegated
end-user OAuth2 (ADR-0014, `auth_mode: delegated-user`) so only content
the user can already see is returned - the same delegated Google
Workspace pattern Arkos proved for Drive writes, exercised here for reads
under Comage's own `sales` role.

Declared for the OKF catalog (ADR-0038); no distinct Agent Runtime route
exists for it yet in v0 - the single `POST /v1/agents/comage/chat`
endpoint only executes `check-deal-status`. Wiring a dedicated route for
this task is v1 scope, matching Tekos's own `find-relevant-docs`/
`check-my-drive-docs` catalog-only tasks.
