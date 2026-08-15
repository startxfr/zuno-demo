---
okf_version: v0.2
type: agent
title: Arkos
description: >-
  Architecture assistant for architects. Helps produce Design & Architecture
  Testimonials (DAT) and prepare Odyssey architecture workshops, drawing on
  the same technical RAG/Confluence knowledge base as Tekos plus Google
  Drive/Docs and Lucidchart.
provenance:
  maintainer: Zuno Demo architecture team
  repository: zuno-demo
verification:
  status: unverified
freshness:
  last_reviewed: "2026-08-05"
sources: []
zuno:
  name: arkos
  status: placeholder
  graph_shape: plan_draft_write
  tasks:
    - draft-architecture-testimonial
  model:
    preferred_classification: C3
    notes: >-
      Placeholder pending v1 build; C3 anticipated because sovereign-marked
      DAT workflows are local-model-only per MEMORY.md section 5.
  access:
    # ADR-0040: agent entitlement group, orthogonal to the `board` business
    # role that governs tool/data permissions inside Arkos.
    groups:
      - agent_arkos
  ui:
    displayName: Arkos
    tileDescription: Architecture DAT and workshop assistant - coming soon.
    color: "#8F4700"
    icon: drafting-compass
---

# Arkos

ADR-0326 (WP-31): Arkos's real OKF task bundle, graph shape and deployment
surface are now merged - `status` stays `placeholder` until the operator
confirms the live acceptance gate passes (WP-31's own Status-updates
section; ADR-0326's "moves placeholder -> active only after the full
common completion pattern passes"), so the portal keeps rendering
"coming soon" and Agent Runtime's generic dispatch keeps 404ing
`/v1/agents/arkos/chat` until that flip happens. No dedicated namespace is
reserved (ADR-0329, supersedes ADR-0023): Arkos's frontend/BFF deploy into
the shared `zuno-ai-run` namespace, same as Tekos.

`zuno.graph_shape: plan_draft_write` (ADR-0342) names Agent Runtime's
LangGraph workflow module for Arkos's chat turns - plan, retrieve
(`knowledge.tech` + `knowledge.project`), draft, write (Drive) -
structurally distinct from Tekos's `retrieve_reason_respond` shape,
proving the graph-shape mechanism WP-30 built generalizes past one
hardcoded workflow. Arkos has no agent-level `zuno.allowed_knowledge`
field either (ADR-0203), for the same reason Tekos doesn't: its knowledge
ceiling is the union of its one task's own `zuno.allowed_knowledge` -
today `[knowledge.tech, knowledge.project]`.

Access group is `agent_arkos` (ADR-0040 entitlement dimension, orthogonal
to the `board` business role that governs tool/data permissions inside
Arkos once active - see `policies/tools/tool-policy.yaml`'s
`drive.document.*`/`confluence.page.*` entries): DATs are reviewed and
approved at board level, so `board` gates what an already-entitled Arkos
session can actually do, matching every other agent's ADR-0040 dimension
split.
