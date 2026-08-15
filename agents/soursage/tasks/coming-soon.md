---
okf_version: v0.2
type: task
title: Coming soon
zuno:
  allowed_tools: []
---

# Coming soon

Soursage is not yet built. Planned tasks (ADR-0349 §6): source new
consultant candidates from LinkedIn; find, among existing consultants,
the best profile for a mission using Workday profile data
(`workday.profile.any.read` - the read-only ADR-0340 scoped capability
already registered by WP-32, gated on the `recrut`/`sales` business
roles once real task declarations exist).

`allowed_tools` stays empty while `status: placeholder` (see
`agent.okf.md`) - a placeholder agent has zero tool-call capability by
construction (ADR-0036), matching it having no running Agent Runtime
workflow at all.
