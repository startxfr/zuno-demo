---
okf_version: v0.2
type: task
title: Answer a finance or billing question
zuno:
  allowed_tools:
    - web_search
  allowed_knowledge:
    - knowledge.project
---

# Answer a finance or billing question

Answer a free-form question about invoicing, billing status or financial
reporting, grounded in any durable `knowledge.project` memory for the
engagement. Falls back to a constrained web search when the internal
corpus has no grounded answer.

This is the task Agent Runtime's `retrieve_reason_respond` graph shape
(`components/agent-runtime/app/graph/shapes/retrieve_reason_respond.py`,
ADR-0342) executes for Finage - the same shape module Tekos's, Comage's
and Advantage's primary tasks run, closed over Finage's own agent/task
data (`app/graph/nodes.py`'s `_make_*` factories). Declares no
`live_read_tool`: unlike Comage's/Arkos's live-read tools, every
sxa.* capability Finage's other tasks declare (`sxa.aggregate.
revenue-by-year`, `sxa.record.lookup`, `sxa.customer.read`, `sxa.quote.
read`) needs structured numeric arguments (year, customer_id, ...), not
a free-text query - it does not fit `tool_call_node`'s generic `{"query":
state["message"]}` calling convention the way a search-shaped capability
does, so those tools stay declared-but-not-live-routed (v1 scope) rather
than forcing a mismatched integration here.

**Documented gap (WP-36's own brief anticipates this)**: no
finance-specific RAG knowledge domain exists in this repository, and
`policies/knowledge/knowledge-policy.yaml`'s `knowledge.sxa-legacy` entry
deliberately excludes `finance` from its `allowed_groups` (ADR-0340's own
access-intent table, WP-32) - legacy commercial data stays narrower than
the live domains even for finance. `allowed_knowledge` above is therefore
`knowledge.project` only; no new domain is invented to fill the gap. This
task never declares the sales or ADV knowledge domains, or any
Salesforce/Aramis capability - Finage proves finance-scoped access
without inheriting broader Sales/ADV access (ADR-0326).
