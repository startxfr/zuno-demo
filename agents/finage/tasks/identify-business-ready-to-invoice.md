---
okf_version: v0.2
type: task
title: Identify business ready to invoice
zuno:
  allowed_tools:
    - sxa.customer.read
    - sxa.quote.read
---

# Identify business ready to invoice

Identify business that has reached the `A facturer`/billable state and
later (MEMORY.md section 9), drawing on the deterministic legacy SXA
customer/quote lookups (WP-23) - never a fuzzy RAG retrieval, since exact
billing state must never be something a chunk approximates (ADR-0017).

Declared for the OKF catalog (ADR-0038); no distinct Agent Runtime route
exists for it yet in v0 - the single `POST /v1/agents/finage/chat`
endpoint only executes `answer-finance-question`. Wiring a dedicated
route for this deterministic-query task is v1 scope, matching every
other agent's own catalog-only tasks.
