---
okf_version: v0.2
type: agent
title: Naveo
description: >-
  Onboarding assistant for new team members. Answers questions about internal processes, tooling and where to find reference material, grounded in the technical RAG corpus and internal Confluence content, and can check the caller's own Drive for onboarding documents.
provenance:
  maintainer: Zuno Demo architecture team
  repository: zuno-demo
verification:
  status: unverified
freshness:
  last_reviewed: "2026-08-15"
sources:
    - "knowledge.tech"
    - "knowledge.project"
zuno:
  name: naveo
  status: placeholder
  graph_shape: retrieve_reason_respond
  primary_task: answer-onboarding-question
  tasks:
    - answer-onboarding-question
  rag:
    top_k: 5
  model:
    preferred_classification: C1
    notes: >-
      Scaffolded by platform/templates/agent/ (ADR-0307/WP-41) - reuses
      the retrieve_reason_respond shape and existing knowledge/tool
      capabilities only, no new external systems (ADR-0410).
  access:
    # ADR-0040: agent entitlement group, orthogonal to the
    # `consultant` business role that governs tool/data
    # permissions inside Naveo (policies/tools/tool-policy.yaml -
    # see this bundle's own NEXT_STEPS.md for the exact policy entries to
    # add).
    groups:
      - agent_naveo
  ui:
    displayName: Naveo
    tileDescription: New-hire onboarding Q&A, for consultants - coming soon.
    color: "#5C6BC0"
    icon: compass
---

# Naveo

Onboarding assistant for new team members. Answers questions about internal processes, tooling and where to find reference material, grounded in the technical RAG corpus and internal Confluence content, and can check the caller's own Drive for onboarding documents.

Conforms to `platform/okf/schema/zuno-okf-v0.2.schema.json` (ADR-0005,
ADR-0038). `status` stays `placeholder` until the operator confirms the
live ADR-0027/ADR-0028 acceptance gate passes (ADR-0326's completion
pattern, the same bar every hand-built agent clears) - see this bundle's
own `NEXT_STEPS.md` for what remains.

Scaffolded by `platform/templates/agent/scaffold_agent.py` (ADR-0307,
roadmap WP-41). No dedicated namespace is reserved (ADR-0329): Naveo's
frontend/BFF deploy into the shared `zuno-ai-run` namespace via the
`zuno.zuno.ai/v1alpha1 AIAgent` CR the operator (ADR-0327/ADR-0308)
reconciles - see `gitops/charts/naveo/templates/aiagent.yaml`.
