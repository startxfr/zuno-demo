---
okf_version: v0.2
type: task
title: Coming soon
zuno:
  allowed_tools: []
---

# Coming soon

Finage is not yet built for this v0 demo. Planned v1 tasks: identify
billable business ("A facturer") and later invoice states; monthly
invoicing reporting (revenue, outstanding amounts, delay, forecast).
Finage may perform controlled status writes but must never execute
financial transactions.

`allowed_tools` stays empty while `status: placeholder` (see
`agent.okf.md`) - a placeholder agent has zero tool-call capability by
construction (ADR-0036), matching it having no running Agent Runtime
workflow at all.
