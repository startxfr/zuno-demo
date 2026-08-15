---
okf_version: v0.2
type: task
title: Produce the monthly invoicing report
zuno:
  allowed_tools:
    - sxa.aggregate.revenue-by-year
    - sxa.record.lookup
---

# Produce the monthly invoicing report

Produce the monthly invoicing report (MEMORY.md section 9: revenue,
outstanding amounts, delay and forecast), drawing on the deterministic
legacy SXA revenue aggregation and record-lookup capabilities (WP-23) -
an exact number, never a RAG-approximated one (ADR-0017).

Declared for the OKF catalog (ADR-0038); no distinct Agent Runtime route
exists for it yet in v0 - the single `POST /v1/agents/finage/chat`
endpoint only executes `answer-finance-question`. Report generation
(text/table + PDF) is v1 scope, not built here.
