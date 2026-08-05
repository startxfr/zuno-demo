---
okf_version: v0.2
type: agent
title: Finage
description: >-
  Finance assistant. Identifies business ready to invoice and produces
  monthly invoice reporting, drawing on sales and invoice data.
provenance:
  maintainer: Zuno Demo architecture team
  repository: zuno-demo
verification:
  status: unverified
freshness:
  last_reviewed: "2026-08-05"
sources: []
zuno:
  name: finage
  status: placeholder
  tasks:
    - coming-soon
  model:
    preferred_classification: C2
    notes: >-
      Placeholder pending v1 build; C2 anticipated for financial/commercial
      data handling consistent with policies/data-classification.
  access:
    # ADR-0040: agent entitlement group, orthogonal to the `finance`
    # business role that governs tool/data permissions inside Finage.
    groups:
      - agent_finage
  ui:
    displayName: Finage
    tileDescription: Billing and invoice reporting assistant - coming soon.
    color: "#5752D1"
    icon: calculator
---

# Finage

v0 scope: status is `placeholder` - this bundle, the reserved
`zuno-agent-finage` namespace and this portal tile are the only things
that exist for Finage in v0 (ADR-0007). `tasks/coming-soon.md` describes
the intended v1 build from `agents/finage/README.md` and `MEMORY.md`
section 9.
