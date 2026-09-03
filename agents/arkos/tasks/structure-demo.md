---
okf_version: v0.2
type: task
title: Structure a demo
zuno:
  allowed_tools: []
  allowed_knowledge: []
  # ADR-0544: this task's preferred candidate (provider-routing.yaml's
  # local-maas/local, qwen3.6-27b-instruct, role `quality`) measured at
  # ~18 tok/s live on 2026-09-03 - 1536 tokens is ~85s, inside scenario
  # 9's 180s ceiling with a 2x margin (evaluations/arkos/scenarios.yaml).
  # ~45s on the fleet-default qwen3.5-9b fallback (~22.5 tok/s warm),
  # ~12s on gpt-oss-20b. Enough for a real 5-7 section demo narrative
  # with talking points, while bounding the runaway generation that made
  # this the one scenario timing out 5/5 under the old 30s default
  # (WP-31) - a symptom root-caused to raw generation speed, not
  # transport, and now guarded structurally rather than by timeout alone.
  max_tokens: 1536
  # ADR-0515: editable starters. Shown in the chat empty state, and in the
  # composer's slash menu (agent-frontend web/src/chat/TaskPromptMenu.tsx).
  # UX only - never parsed or enforced server-side, and picking one does NOT
  # select this task: the chat route always runs primary_task (ADR-0342).
  prompt_examples:
    - "Structure a 30-minute platform demo for a technical audience."
    - "How should I sequence a demo showing GitOps from commit to running pod?"
---

# Structure a demo

Structure a customer demo narrative - what to show, in what order, and the
key talking points for each section - directly in the chat reply. Distinct
from `draft-architecture-testimonial`'s long-form DAT/Drive workflow and
from `workshop-presentation`'s Odyssey workshop material: a demo narrative
is a short, conversational deliverable, never a saved document.

Declared for the OKF catalog and reached the same way `write-code` is
(ADR-0417's precedent): a heuristic-triggered, early-exit branch of
Arkos's single live `plan_draft_write` graph
(`app/graph/arkos_nodes.py::demo_node`), reachable only via
`route_after_plan` - never runs `retrieve_node`, so this call's payload is
only the user's own message. `primary_task` stays
`draft-architecture-testimonial`; `GraphFactory` never builds a graph for
`structure-demo` directly - the task name is used only as the
`ModelRouter.invoke_with_fallback` routing label, same "declared, not
live-routed by itself" status `write-code` already has.

Unlike `write-code`, this task's system prompt is a real file
(`prompts/structure-demo.md`) rather than a Python string literal -
ADR-0419 established that prompt text belongs in Markdown, not inline in
`arkos_nodes.py`, and there is no reason for a new task to repeat the
older pattern.

`allowed_tools`/`allowed_knowledge` are deliberately empty, same reasoning
as `write-code`: this branch runs directly from `plan_node`, before
`retrieve_node`, and makes no MCP tool call of its own.

v0 scope, honestly: this produces a narrative grounded only in the
conversation itself, not the technical RAG corpus or Confluence content
`draft-architecture-testimonial`/`workshop-presentation` retrieve. A demo
script that cites the same DAT/project material is later work, once this
early-exit shape proves useful on its own - the same kind of deferral the
DAT task's own "v0 scope, honestly" section already makes for its full
workflow.
