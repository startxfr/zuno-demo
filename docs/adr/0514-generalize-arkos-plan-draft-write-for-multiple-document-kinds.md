# ADR-0514: Generalize Arkos's plan_draft_write shape for multiple document kinds

- **Status:** Implemented - see `components/agent-runtime/app/graph/arkos_nodes.py`, `agents/arkos/tasks/workshop-presentation.md` and `components/agent-runtime/tests/test_arkos_nodes.py` (WP-7, 2026-08-20)
- **Target:** OKF v0.1
- **Date:** 2026-08-20
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0342's `plan_draft_write` graph shape was built and has stayed, since
WP-31, structurally bound to one task: `retrieve_node`, `draft_node`,
`reflect_node` and `write_node` all reference the module-level
`_DRAFT_TASK` singleton (`draft-architecture-testimonial`) directly, and
that module's own docstring notes the shape "stays bound to Arkos's own
module-level singletons rather than being agent/task-parameterized." That
was a reasonable simplification when only one task ever reached the
retrieve/draft/write path - `write-code` (ADR-0417) and `structure-demo`
(this same WP) both prove a *second* task can exist without needing this,
because they early-exit right after `plan_node` and never touch
`retrieve_node`/`draft_node`/`write_node` at all.

Arkos's own `agent.okf.md` description has named "prepare Odyssey
architecture workshops" as an initial task since before any code existed
(`MEMORY.md:151/165`), and unlike `structure-demo` a workshop
presentation is exactly the kind of long-form, RAG-grounded, Drive-saved
deliverable `draft-architecture-testimonial` already produces - reusing
`write-code`'s early-exit shape for it would mean no retrieval, no
Confluence context and no saved document, which is a materially worse
fit than accepting the coupling this ADR removes.

## Decision

1. **`plan_node` classifies a `doc_plan.kind`** (`"dat"` by default, or
   `"workshop"` when the message matches a new `_WORKSHOP_TRIGGER_PATTERN`
   - the keywords `workshop`/`odyssey`), alongside the topic it already
   extracts. This classification happens once, at the same point
   `route_after_plan` already decides between `code`/`demo`/`retrieve` -
   it does not add a new graph node or edge, only a new field on the
   existing `doc_plan` state key.
2. **`retrieve_node`, `draft_node`, `reflect_node` and `write_node` each
   resolve the active `TaskDefinition`** from `doc_plan.kind` via a new
   `_active_task(state)` helper, instead of referencing `_DRAFT_TASK`
   module-wide. A second task, `workshop-presentation`, is loaded at
   module scope with the same fail-fast `RuntimeError` guard `_DRAFT_TASK`
   has.
3. **The reflect prompt-slot mechanism (ADR-0419) generalizes the same
   way**: `workshop-presentation` declares its own `zuno.prompts.reflect`
   slot (`prompts/workshop-presentation--reflect.md`), resolved through a
   new `_resolve_reflect_slot(task, fallback_prompt)` helper shared by
   both tasks instead of the two constants `reflect_node` used to read
   directly. This is the mechanism's first second consumer - proof it
   generalizes past the one task ADR-0419 built it for, the same kind of
   proof ADR-0342 itself was originally written to provide for graph
   shapes.
4. **No change to `write-code`/`structure-demo`'s early-exit shape or to
   `route_after_plan`'s three branches** (`code`/`demo`/`retrieve`) - kind
   classification is orthogonal to that routing decision and only matters
   once a turn is already on the `retrieve` path.

## Consequences

- A third document kind (or a second agent reusing this shape) is now a
  bounded extension: a new task file + prompt(s) + one more branch in
  `_active_task`'s kind lookup, not a new set of graph nodes.
- `plan_draft_write.py`'s own docstring claim that its nodes stay
  "agent/task-parameterized: no" is now only true at the graph-shape
  level (still one compiled graph, still Arkos-only) - the nodes
  themselves are task-parameterized *within* that one shape as of this
  ADR.
- Model routing is unaffected: `policies/model-routing/model-routing-
  policy.yaml`'s per-(agent, task) `prefer:` list already applies
  independently of which task a call names (ADR-0412), so
  `workshop-presentation` gets its own entry the same way
  `draft-architecture-testimonial` has one, with no new mechanism needed
  for the reflect-slot call specifically (classification ceiling, not a
  separate policy row, is what changes which entries are eligible at that
  call).

## Related ADRs

ADR-0342 (graph shapes), ADR-0416 (reflect self-review, C2 ceiling),
ADR-0417 (early-exit branch precedent), ADR-0419 (prompt slots this
extends to a second task).
