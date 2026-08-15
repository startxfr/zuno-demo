---
okf_version: v0.2
type: task
title: Compare historical deals
zuno:
  allowed_tools:
    - sxa.opportunity.search
    - sxa.aggregate.revenue-by-year
  allowed_knowledge:
    - knowledge.sxa-legacy
---

# Compare historical deals

Answer a question that needs historical/legacy sales data - deals or
revenue figures predating the live Salesforce cutover - using the
`knowledge.sxa-legacy` domain and the deterministic `sxa.*` capabilities
(WP-23) over the imported legacy SXA snapshot, never the live/current
`knowledge.sales`/`salesforce.opportunity.*` surfaces (ADR-0206: current
Salesforce knowledge and legacy SXA are kept strictly separate, in both
directions).

Declared for the OKF catalog (ADR-0038); no distinct Agent Runtime route
exists for it yet in v0 - the single `POST /v1/agents/comage/chat`
endpoint only executes `check-deal-status`. Wiring a dedicated route for
this task is v1 scope, matching Tekos's own `find-relevant-docs`/
`check-my-drive-docs` catalog-only tasks.
