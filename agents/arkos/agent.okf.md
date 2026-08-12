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
  tasks:
    - coming-soon
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

v0 scope: status is `placeholder` - this bundle and this portal tile are
the only things that exist for Arkos in v0 (ADR-0007). No dedicated
namespace is reserved (ADR-0329, supersedes ADR-0023): a future active
Arkos deployment would run in the shared `zuno-ai-run` namespace.
`tasks/coming-soon.md` describes the intended v1 build from
`agents/arkos/README.md` and `MEMORY.md` sections 8-9. Access group is
`board` per ADR-0040's business-role dimension - intentional, not the
`agent_arkos` entitlement group: DATs are reviewed and approved at board
level, so tool/data permissions inside Arkos are gated on `board`
membership rather than on the broader (and orthogonal) architects'
entitlement to the agent itself.
