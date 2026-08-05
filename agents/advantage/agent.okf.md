---
okf_version: v0.2
type: agent
title: Advantage
description: >-
  Sales administration assistant. Surfaces new business whose client
  purchase order has just been received and produces monthly in-progress
  sales reporting, drawing on the shared sales data.
provenance:
  maintainer: Zuno Demo architecture team
  repository: zuno-demo
verification:
  status: unverified
freshness:
  last_reviewed: "2026-08-05"
sources: []
zuno:
  name: advantage
  status: placeholder
  tasks:
    - coming-soon
  model:
    preferred_classification: C2
    notes: >-
      Placeholder pending v1 build; C2 anticipated for commercial sales-data
      handling consistent with policies/data-classification.
  access:
    # ADR-0040: agent entitlement group, orthogonal to the `adv` business
    # role that governs tool/data permissions inside Advantage.
    groups:
      - agent_advantage
  ui:
    displayName: Advantage
    tileDescription: Sales administration and PO tracking - coming soon.
    color: "#4CB140"
    icon: clipboard-check
---

# Advantage

v0 scope: status is `placeholder` - this bundle, the reserved
`zuno-agent-advantage` namespace and this portal tile are the only things
that exist for Advantage in v0 (ADR-0007). `tasks/coming-soon.md`
describes the intended v1 build from `agents/advantage/README.md` and
`MEMORY.md` section 9.
