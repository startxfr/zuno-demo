---
okf_version: v0.2
type: task
title: Write code
zuno:
  allowed_tools: []
  allowed_knowledge: []
  # ADR-0515: editable starters. Shown in the chat empty state, and in the
  # composer's slash menu (agent-frontend web/src/chat/TaskPromptMenu.tsx).
  # UX only - never parsed or enforced server-side, and picking one does NOT
  # select this task: the chat route always runs primary_task (ADR-0342).
  prompt_examples:
    - "Write a Helm template that renders a Route only when ingress is enabled."
    - "Generate a shell script that waits for an Argo CD Application to become Synced and Healthy."
---

# Write code

Generate code, configuration or a script (Terraform, Ansible, Kubernetes
manifests, Helm, shell, Python, Go, ...) directly in the chat reply -
distinct from `draft-architecture-testimonial`'s long-form DAT/Drive
workflow, which a request like this has nothing to do with.

Declared for the OKF catalog (ADR-0417), same "declared, not live-routed
by itself" status Finage's non-primary tasks already have (`primary_task`
stays `draft-architecture-testimonial` - `GraphFactory` never builds a
graph for `write-code` directly). It is referenced only as the
`task_name` label `app/graph/arkos_nodes.py::code_node` passes to
`ModelRouter.invoke_with_fallback` for one heuristic-triggered, early-exit
branch of Arkos's single live `plan_draft_write` graph - the same
task-name-as-routing-label mechanism ADR-0416 established for
`reflect_node`'s fixed-classification override, applied here as a fixed
task-name override instead. `allowed_tools`/`allowed_knowledge` are
deliberately empty: this branch runs directly from `plan_node`, before
`retrieve_node`, and makes no MCP tool call of its own.

`policies/model-routing/model-routing-policy.yaml`'s `(arkos, write-code)`
entry is `strict: true`, `prefer: [mistral-codestral]` - Codestral only,
no local/SaaS fallback. If the call fails for any reason (including the
account running low on credits), the turn fails explicitly rather than
silently substituting a different model - the concrete, buildable form of
"ask the user to move to another model" a live credit-balance check would
otherwise require (see ADR-0417's Accepted risks).
