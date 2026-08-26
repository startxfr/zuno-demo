---
okf_version: v0.2
type: task
title: Compare historical deals
zuno:
  allowed_tools: []
  allowed_knowledge:
    - knowledge.sxa-legacy
---

# Compare historical deals

Answer a question that needs historical/legacy sales data - deals or
revenue figures predating the live Salesforce cutover - by retrieving from
the `knowledge.sxa-legacy` domain, never the live/current
`knowledge.sales`/`salesforce.opportunity.*` surfaces (ADR-0206: current
Salesforce knowledge and legacy SXA are kept strictly separate, in both
directions).

**Retrieval only, and answers must be framed as such (ADR-0219).** This
task declares no tools. The deterministic `sxa.*` capabilities it was
originally built on are gone: SXA is the company's closed pre-2021 record,
not a live system, so there is no store of record for an exact-figure tool
to be authoritative against. Any figure this task reports is read out of
retrieved historical records and must be attributed to them - it is not a
computed aggregate, and it must never be presented as one.

Declared for the OKF catalog (ADR-0038); no distinct Agent Runtime route
exists for it yet in v0 - the single `POST /v1/agents/comage/chat`
endpoint only executes `check-deal-status`. Wiring a dedicated route for
this task is v1 scope, matching Tekos's own `find-relevant-docs`/
`check-my-drive-docs` catalog-only tasks.
