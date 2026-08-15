---
okf_version: v0.2
type: task
title: Check my Drive and mail
zuno:
  allowed_tools:
    - list_drive_files
    - read_gmail
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
