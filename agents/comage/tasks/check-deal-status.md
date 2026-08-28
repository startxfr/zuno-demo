---
okf_version: v0.2
type: task
title: Check deal status
zuno:
  allowed_tools:
    - salesforce.opportunity.read
    - web_search
    # ADR-0415: stable-diffusion-xl via OVHcloud AI Endpoints. Comage is
    # the only agent with this capability (policy update: photorealistic
    # generation elsewhere was removed), and even here it's scoped to
    # genuine marketing-visual requests only, never deal-status charts/
    # mockups - see prompts/check-deal-status.md's system prompt, which is
    # where that scope is actually enforced (this task has only the one
    # live-routed primary task, so there's no separate task boundary to
    # gate on).
    - image.generation.create
    # ADR-0516: Mermaid-to-SVG rendering, for deal-status visuals needing
    # precise structure (e.g. a real chart from actual figures) - this is
    # the tool for ordinary deal-status charts/mockups now, not the one
    # above.
    - diagram.generation.create
  live_read_tool: salesforce.opportunity.read
  allowed_knowledge:
    - knowledge.sales
    - knowledge.project
  # ADR-0515: editable starters. Shown in the chat empty state, and in the
  # composer's slash menu (agent-frontend web/src/chat/TaskPromptMenu.tsx).
  # UX only - never parsed or enforced server-side, and picking one does NOT
  # select this task: the chat route always runs primary_task (ADR-0342).
  prompt_examples:
    - "What is the current stage of the Startx renewal opportunity?"
    - "Which opportunities are expected to close this quarter?"
    - "What is the amount on the largest open deal in my pipeline?"
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
