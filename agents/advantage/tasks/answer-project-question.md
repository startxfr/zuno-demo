---
okf_version: v0.2
type: task
title: Answer a project or bid question
zuno:
  allowed_tools:
    - web_search
    # ADR-0415: stable-diffusion-xl via OVHcloud AI Endpoints, offered to
    # the reasoning model as a callable tool for project/bid questions
    # that call for a visual (mockup, diagram).
    - image.generation.create
  allowed_knowledge:
    - knowledge.adv
    - knowledge.project
    - knowledge.sxa
---

# Answer a project or bid question

Answer a free-form question about project/delivery status, ownership,
business-unit or bid/proposal support, grounded in `knowledge.adv`
(no ingestion adapter since ADR-0218 - its source is an open decision)
and any durable `knowledge.project` memory for the engagement. Falls back to a
constrained web search when the internal corpus has no grounded answer.

This is the task Agent Runtime's `retrieve_reason_respond` graph shape
(`components/agent-runtime/app/graph/shapes/retrieve_reason_respond.py`,
ADR-0342) executes for Advantage - the same shape module Tekos's and
Comage's primary tasks run, closed over Advantage's own agent/task data
(`app/graph/nodes.py`'s `_make_*` factories). Declares no `live_read_tool`:
no live adv MCP capability exists, and ADR-0218 removed the batch adapter
that used to fill `knowledge.adv`, so this task is indexed-read only -
`tool_call_node` cleanly no-ops rather than attempting a live call
(ADR-0326).

ADR-0326's signature proof for this slice: `allowed_knowledge` above
never includes Comage's own current-sales knowledge domain or
`knowledge.sxa-legacy`, and `allowed_tools` never includes any
live-CRM/legacy-SXA MCP capability - Advantage proves the cross-domain
authorization boundary by explicit omission, not by a runtime filter. Any
cross-domain commercial access this agent might need in a future
iteration must be added here explicitly and policy-controlled, never
inherited from Comage.

`knowledge.sxa` (ADR-0217/WP-067) is the one exception, added deliberately:
a weekly, already-anonymized commercial corpus distinct from
`knowledge.sxa-legacy` - opened to Advantage from the start, unlike
`knowledge.sxa-legacy`'s sales/board-only restriction (WP-35's negative
test for Advantage against `knowledge.sxa-legacy` specifically is
unaffected by this grant).
