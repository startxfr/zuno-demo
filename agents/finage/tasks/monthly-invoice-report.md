---
okf_version: v0.2
type: task
title: Produce the monthly invoicing report
zuno:
  allowed_tools:
    - salesforce.opportunity.read
  allowed_knowledge:
    - knowledge.project
    - knowledge.sxa-legacy
  project_required: true
---

# Produce the monthly invoicing report

Produce the monthly invoicing report (MEMORY.md section 9: revenue,
outstanding amounts, delay and forecast) over the `knowledge.sxa-legacy`
historical corpus.

**Retrieval only; figures are historical and must be attributed
(ADR-0219).** This task was built on `sxa.aggregate.revenue-by-year` and
`sxa.record.lookup`, whose whole point was an exact number rather than a
RAG-approximated one (ADR-0017). Those capabilities are gone: SXA is the
company's closed pre-2021 record, and a frozen corpus has no store of
record for an aggregation tool to compute against. Every figure this task
reports is now read out of retrieved records and must be attributed to
them. It must not present a summed or derived total as an authoritative
aggregate, and it must not imply the numbers describe the current period.

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
