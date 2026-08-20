---
okf_version: v0.2
type: task
title: Draft an architecture testimonial
zuno:
  allowed_tools:
    - confluence.page.read
    - confluence.page.search
    - drive.document.create
    - drive.document.update
    - git.repository.read
    - git.repository.list
    - git.repository.private.read
    - git.repository.private.list
    - git.file.write
    - git.repository.create
    # ADR-0415: stable-diffusion-xl via OVHcloud AI Endpoints, offered to
    # the drafting model as a callable tool - it decides whether a given
    # DAT/workshop request needs an illustration.
    - image.generation.create
  allowed_knowledge:
    - knowledge.tech
    - knowledge.project
---

# Draft an architecture testimonial

Draft a Design & Architecture Testimonial (DAT) - a long-form document
describing an architecture, grounded in the Tekos technical RAG corpus and
internal Confluence content, and save it to the caller's Google Drive as a
new or updated Google Doc.

This is the task Agent Runtime's `plan_draft_write` graph shape
(`components/agent-runtime/app/graph/shapes/plan_draft_write.py`, ADR-0342)
executes: plan (derive the document's topic/title from the request) ->
retrieve (`knowledge.tech` + `knowledge.project`, topic-driven) -> draft
(long-form generation) -> reflect (self-review pass, ADR-0416) -> write
(`drive.document.create`/`.update`) - materially different from Tekos's
retrieve/tool_call/reason/respond shape, proving a second agent can run a
genuinely different workflow on the same shared runtime (ADR-0326).

ADR-0416: the reflect step prefers `ovhcloud-gpt-oss-120b` (same OVHcloud
AI Endpoints account as the `image.generation.create` tool above) for its
self-review pass over the draft - evaluated at a fixed C2 ceiling since
that call's payload is only the draft's own prose, never the raw
retrieved/Confluence context draft_node was grounded in. Still honors any
source-level `local_only_required` restriction that turn's retrieval may
have set (ADR-0035) - the C2 ceiling overrides classification escalation
only, never that separate restriction.

v0 scope, honestly: this proves the plan -> retrieve -> draft -> write
mechanism end to end in one turn. The full v1 DAT workflow described in
`docs/agents/arkos.md`/MEMORY.md section 8 - collect -> outline ->
explicit user review -> generation -> review -> final Google Doc, with
resumable intermediate state and optional Lucidchart diagrams - is staged
work: the explicit-review checkpoints between stages are a later
iteration, not built by this task. Live Jira is deferred until its MCP
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
