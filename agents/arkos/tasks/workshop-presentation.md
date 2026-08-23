---
okf_version: v0.2
type: task
title: Prepare an Odyssey workshop presentation
zuno:
  allowed_tools:
    - confluence.page.read
    - confluence.page.search
    - git.repository.read
    - git.repository.list
    - git.repository.private.read
    - git.repository.private.list
    - git.file.write
    - git.repository.create
    # ADR-0516: same as draft-architecture-testimonial.md's task - see
    # that task's own comment (`image.generation.create` was removed from
    # both tasks by this policy update; photorealistic image generation
    # is now Comage-only, scoped to marketing visuals).
    - diagram.generation.create
  allowed_knowledge:
    - knowledge.tech
    - knowledge.project
  # ADR-0419/ADR-0514: same reflect prompt-slot mechanism draft-
  # architecture-testimonial.md's task established - a self-review pass
  # over draft_node's own output, evaluated at a fixed C2 ceiling. Second
  # real consumer of the mechanism, proving it generalizes past the one
  # task it was built for.
  prompts:
    reflect:
      classification_ceiling: C2
---

# Prepare an Odyssey workshop presentation

Draft an Odyssey architecture workshop presentation - a structured
document covering what the workshop will present - grounded in the Tekos
technical RAG corpus and internal Confluence content, and return it in
the reply.

`drive.document.create`/`.update` are deliberately not in `allowed_tools`,
same reasoning as `draft-architecture-testimonial`'s own task file: no
`google-workspace` MCP server is deployed in this cluster at all, so
`write_node`'s unconditional Drive-write attempt now gets a fast,
deterministic 403 from MCP Gateway instead of a slow/uncertain call to
an absent host, and its existing `except McpClientError` fallback
returns the draft as the chat reply either way. Re-add both once a real
`google-workspace` MCP server exists.

Reuses the exact `plan_draft_write` shape (ADR-0342) and same
plan -> retrieve -> draft -> reflect -> write nodes
`draft-architecture-testimonial` already runs
(`components/agent-runtime/app/graph/shapes/plan_draft_write.py`) - not a
new graph branch. `plan_node` classifies the request's `doc_plan.kind` as
`"workshop"` (trigger words `workshop`/`odyssey`, ADR-0514) instead of the
default `"dat"`, and `retrieve_node`/`draft_node`/`reflect_node`/
`write_node` resolve this task instead of `draft-architecture-
testimonial`'s from that field - see ADR-0514 for why this is a second
"kind" through the same shape rather than a new one.

v0 scope, honestly: this produces one workshop presentation document in
one turn, the same "prove the mechanism end to end" scope
`draft-architecture-testimonial` already carries. The full Odyssey
workflow described in MEMORY.md section 8 - starting from an existing
project Google Sheet and Google Slides template library in Drive, and
producing workshop material, an architecture/build/run roadmap, slides
*and* workshop reports as separate artifacts - is staged work: this task
drafts the presentation content only, not the multi-artifact
Sheet/Slides/roadmap/report pipeline. Live Jira is deferred the same way
the DAT task's own scope note defers it; Confluence read/search are live
today.

`allowed_tools`/`allowed_knowledge` and the `git.*` visibility rules are
identical to `draft-architecture-testimonial`'s (ADR-0121) - see that
task's own file for the exact public/private/write breakdown, not
duplicated here since both tasks share one agent-level authorization
ceiling (`AgentDefinition.declared_tools()`/`declared_knowledge()`).
