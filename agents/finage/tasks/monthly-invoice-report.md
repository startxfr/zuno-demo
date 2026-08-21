---
okf_version: v0.2
type: task
title: Produce the monthly invoicing report
zuno:
  allowed_tools:
    - sxa.aggregate.revenue-by-year
    - sxa.record.lookup
    - salesforce.opportunity.read
  allowed_knowledge:
    - knowledge.project
  project_required: true
---

# Produce the monthly invoicing report

Produce the monthly invoicing report (MEMORY.md section 9: revenue,
outstanding amounts, delay and forecast), drawing on the deterministic
legacy SXA revenue aggregation and record-lookup capabilities (WP-23) -
an exact number, never a RAG-approximated one (ADR-0017).

`zuno.project_required: true` (ADR-0512/WP-55): this report only makes
sense for one client engagement, so Agent Runtime refuses to execute it
until the prompt-collected project (name or Salesforce id) is verified
via `salesforce.opportunity.read` under the caller's own identity,
fail-closed. That capability is declared here only for this binding
check - it is a standalone pre-graph call that never populates the
model's tool results or context, so `answer-finance-question`'s "Finage
has no live Salesforce access" boundary (ADR-0326) is unaffected: no
Salesforce record content ever reaches this task's answer path either. A
verified binding scopes `knowledge.project` retrieval to that engagement
and draws its ADR-0511 project quota first.

Declared for the OKF catalog (ADR-0038); no distinct Agent Runtime route
exists for it yet in v0 - the single `POST /v1/agents/finage/chat`
endpoint only executes `answer-finance-question`. Report generation
(text/table + PDF) is v1 scope, not built here; the project_required
mark and binding enforcement above are real and schema/contract-tested
today, and take effect automatically the moment this task is ever made
`primary_task`-routed.
