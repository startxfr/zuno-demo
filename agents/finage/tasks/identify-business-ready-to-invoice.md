---
okf_version: v0.2
type: task
title: Identify business ready to invoice
zuno:
  allowed_tools:
    - salesforce.opportunity.read
  allowed_knowledge:
    - knowledge.project
    - knowledge.sxa-legacy
  project_required: true
---

# Identify business ready to invoice

Identify business that has reached the `A facturer`/billable state and
later (MEMORY.md section 9), by retrieving the relevant customer and quote
records from the `knowledge.sxa-legacy` historical corpus.

**Retrieval only, and billing state is historical, not current
(ADR-0219).** This task was built on the deterministic `sxa.customer.read`/
`sxa.quote.read` lookups, on the reasoning that exact billing state must
never be something a chunk approximates (ADR-0017). Those capabilities are
gone, and the reasoning no longer applies the way it did: SXA is the
company's closed pre-2021 record, so there is no live billing system for a
deterministic tool to be exact *about*. What this task now reports is the
billing state as it stood in that historical record, attributed to the
records it came from - never presented as the current state of an
outstanding invoice.

`zuno.project_required: true` (ADR-0512/WP-55): this task only makes
sense inside one client engagement, so Agent Runtime refuses to execute
it until the prompt-collected project (name or Salesforce id) is verified
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
endpoint only executes `answer-finance-question`. Wiring a dedicated
route for this deterministic-query task is v1 scope, matching every
other agent's own catalog-only tasks; the project_required mark and
binding enforcement above are real and schema/contract-tested today, and
take effect automatically the moment this task is ever made
`primary_task`-routed.
