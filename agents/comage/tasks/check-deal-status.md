---
okf_version: v0.2
type: task
title: Check deal status
zuno:
  allowed_tools:
    - salesforce.opportunity.read
    - web_search
  live_read_tool: salesforce.opportunity.read
  allowed_knowledge:
    - knowledge.sales
    - knowledge.project
---

# Check deal status

Answer a free-form question about an opportunity or the pipeline, preferring
`knowledge.sales` (asynchronously ingested, indexed Salesforce content) for
ordinary semantic reads. A question asking for a mutable field's CURRENT
value (stage, amount) - or any retrieval that lands on `knowledge.sales`
itself, which is freshness-sensitive by policy
(`knowledge/sales/domain.yaml`'s tight `current-state-read` window) -
triggers a live `salesforce.opportunity.read` call instead of trusting the
index alone (ADR-0205).

This is the task Agent Runtime's `retrieve_reason_respond` graph shape
(`components/agent-runtime/app/graph/shapes/retrieve_reason_respond.py`,
ADR-0342) executes for Comage - the same shape module Tekos's
`answer-technical-question` runs, closed over Comage's own agent/task data
instead (`app/graph/nodes.py`'s `_make_*` factories). Proves the shape
genuinely generalizes past one hardcoded agent (ADR-0326), not just its
topology: Comage's live-read tool is Salesforce, not Confluence
(`zuno.live_read_tool` above), and its freshness-sensitive domain is
`knowledge.sales`, not a stale-document check.
