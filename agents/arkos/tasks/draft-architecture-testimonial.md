---
okf_version: v0.2
type: task
title: Draft an architecture testimonial
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
    # ADR-0516: Mermaid-to-SVG rendering, offered to the drafting model as
    # a callable tool for architecture/sequence/relationship diagrams
    # needing precise structure or legible text. `image.generation.create`
    # (ADR-0415, stable-diffusion-xl) was offered here too until this
    # policy update - photorealistic image generation is now Comage-only,
    # scoped to marketing visuals; Arkos's own "does this need an
    # illustration" cases are all diagram-shaped in practice, so
    # generate_diagram alone covers them.
    - diagram.generation.create
    # ADR-0355/WP-074: the read-only half of the AAP audits only. Arkos
    # writes architecture narratives, so live platform state is genuinely
    # useful context; launching cluster automation is not something an
    # architecture-drafting task can justify, so aap.cluster.audit is
    # deliberately absent here (see agents/tekos/tasks/
    # answer-technical-question.md, which does declare it).
    - aap.platform.audit
  allowed_knowledge:
    - knowledge.tech
    - knowledge.project
  # ADR-0419: the reflect step (app/graph/arkos_nodes.py::reflect_node,
  # ADR-0416) is a distinct call within this same task - a self-review
  # pass over draft_node's own output, evaluated at a fixed C2 ceiling
  # rather than this task's ambient classification. Declared here instead
  # of hardcoded in Python; prompts/draft-architecture-testimonial--reflect.md
  # is its prompt text.
  prompts:
    reflect:
      classification_ceiling: C2
  # ADR-0515: editable starters. Shown in the chat empty state, and in the
  # composer's slash menu (agent-frontend web/src/chat/TaskPromptMenu.tsx).
  # UX only - never parsed or enforced server-side, and picking one does NOT
  # select this task: the chat route always runs primary_task (ADR-0342).
  prompt_examples:
    - "Draft an architecture testimonial for a customer running OpenShift with Keycloak-backed SSO."
    - "Write a Design and Architecture Testimonial covering a GitOps delivery chain based on Argo CD."
---

# Draft an architecture testimonial

Draft a Design & Architecture Testimonial (DAT) - a long-form document
describing an architecture, grounded in the Tekos technical RAG corpus and
internal Confluence content, and return it in the reply.

This is the task Agent Runtime's `plan_draft_write` graph shape
(`components/agent-runtime/app/graph/shapes/plan_draft_write.py`, ADR-0342)
executes: plan (derive the document's topic/title from the request) ->
retrieve (`knowledge.tech` + `knowledge.project`, topic-driven) -> draft
(long-form generation) -> reflect (self-review pass, ADR-0416) -> write -
materially different from Tekos's retrieve/tool_call/reason/respond
shape, proving a second agent can run a genuinely different workflow on
the same shared runtime (ADR-0326).

`drive.document.create`/`.update` are deliberately not in `allowed_tools`:
no `google-workspace` MCP server is deployed anywhere in this cluster -
not "unverified," genuinely absent. `write_node` still attempts the call
unconditionally (no code branch skips it); MCP Gateway's ADR-0011
intersection now denies it with a fast, deterministic 403 (this task
never declared the capability) instead of a slow/uncertain connection
attempt to a host that doesn't exist, and `write_node`'s existing
`except McpClientError` fallback returns the draft as the chat reply -
the same outcome a live Drive write failure would have produced, just
without depending on an absent service to get there. Re-add both once a
real `google-workspace` MCP server exists.

ADR-0416: the reflect step prefers `ovhcloud-gpt-oss-120b` (OVHcloud AI
Endpoints) for its self-review pass over the draft - evaluated at a fixed
C2 ceiling since
that call's payload is only the draft's own prose, never the raw
retrieved/Confluence context draft_node was grounded in. Still honors any
source-level `local_only_required` restriction that turn's retrieval may
have set (ADR-0035) - the C2 ceiling overrides classification escalation
only, never that separate restriction.

v0 scope, honestly: this proves the plan -> retrieve -> draft -> write
mechanism end to end in one turn. The full v1 DAT workflow described in
`docs/agents/arkos.md`/MEMORY.md section 8 - collect -> outline ->
explicit user review -> generation -> review -> final Google Doc, with
resumable intermediate state - is staged work: the explicit-review
checkpoints between stages are a later iteration, not built by this task.
"Optional Lucidchart diagrams" from that same original plan is superseded
by ADR-0516's `generate_diagram` (self-hosted Mermaid rendering) - built,
not staged; a real Lucidchart integration was never built (its
`components/mcp-servers/lucidchart` placeholder was removed when ADR-0516
was closed out) and this task no longer depends on it. Live Jira is deferred until its MCP
server exists (WP-02's template, not yet scheduled for Jira); Confluence
read/search are live today (`components/mcp-servers/confluence`, ADR-0117).

ADR-0121: the six `git.*` entries add GitHub/GitLab repository access
(`components/mcp-servers/git-forge`, ADR-0120) so Arkos can cite/reference
real source repositories in a testimonial and, when asked, publish
supporting material as a new or updated repository. Arkos's exact
authorization shape:
- `git.repository.read`/`git.repository.list` - **public** repositories,
  both GitHub and GitLab.
- `git.repository.private.read`/`git.repository.private.list` - private/
  internal repositories, **GitLab only** (this server never grants
  private GitHub access to anyone, ADR-0121).
- `git.file.write` - commits **only ever land in public repositories**,
  on either provider, server-enforced regardless of what Arkos requests.
- `git.repository.create` - unrestricted by visibility (Arkos chooses).
No `git.repository.fork`/`git.repository.delete` - unused by this task;
`delete_repository` always refuses regardless of declaration anyway.
