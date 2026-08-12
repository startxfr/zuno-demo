---
okf_version: v0.2
type: agent
title: Comage
description: >-
  Sales assistant. Prioritizes follow-ups, surfaces deals still missing a
  client purchase order, and produces a weekly sales synthesis, drawing on
  sales data and the user's own Gmail mailbox.
provenance:
  maintainer: Zuno Demo architecture team
  repository: zuno-demo
verification:
  status: unverified
freshness:
  last_reviewed: "2026-08-05"
sources: []
zuno:
  name: comage
  status: placeholder
  tasks:
    - coming-soon
  model:
    preferred_classification: C2
    notes: >-
      Placeholder pending v1 build; C2 anticipated because Gmail content
      requires context filtering rather than unrestricted SaaS use.
  access:
    # ADR-0040: agent entitlement group, orthogonal to the `sales` business
    # role that governs tool/data permissions inside Comage.
    groups:
      - agent_comage
  ui:
    displayName: Comage
    tileDescription: Sales follow-up and pipeline assistant - coming soon.
    color: "#F0AB00"
    icon: handshake
---

# Comage

v0 scope: status is `placeholder` - this bundle and this portal tile are
the only things that exist for Comage in v0. No dedicated namespace is
reserved (ADR-0329, supersedes ADR-0023): a future active Comage
deployment would run in the shared `zuno-ai-run` namespace. No Agent
Runtime task graph, FE or BFF is deployed (ADR-0007,
`platform/architecture/agent-platform-separation.md`).
`tasks/coming-soon.md` describes the intended v1 build from
`agents/comage/README.md` and `MEMORY.md` section 9, kept here so
onboarding Comage later is primarily a `status: active` flip plus real
task implementation, not a redesign.
