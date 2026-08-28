---
okf_version: v0.2
type: task
title: Answer a finance or billing question
zuno:
  allowed_tools:
    - web_search
  allowed_knowledge:
    - knowledge.project
    - knowledge.sxa-legacy
  # ADR-0515: editable starters. Shown in the chat empty state, and in the
  # composer's slash menu (agent-frontend web/src/chat/TaskPromptMenu.tsx).
  # UX only - never parsed or enforced server-side, and picking one does NOT
  # select this task: the chat route always runs primary_task (ADR-0342).
  prompt_examples:
    - "What is the invoicing status for this engagement?"
    - "How much is still outstanding on this account?"
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
`live_read_tool`: this task's only tool is `web_search`, and Finage's
other tasks declare no live-read capability either since ADR-0219 removed
the deterministic `sxa.*` surface. `tool_call_node` cleanly no-ops rather
than attempting a live call.

**Documented gap (WP-36's own brief anticipates this), now closed on the
retrieval side**: `finance` is in `knowledge.sxa-legacy`'s
`allowed_groups` (ADR-0219 widened it to the union of what that domain and
the duplicate ADR-0217 domain granted), so `allowed_knowledge` above is
`knowledge.project` and `knowledge.sxa-legacy` - still never
`knowledge.sales` or `knowledge.adv`. What remains genuinely open is the
deterministic side: Finage has no exact-figure capability at all, because
SXA is a closed pre-2021 record with no live billing system behind it. This
task still declares no Salesforce capability - Finage proves finance-scoped
access without inheriting broader Sales/ADV access (ADR-0326).
