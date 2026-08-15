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
