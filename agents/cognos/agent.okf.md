---
okf_version: v0.2
type: agent
title: Cognos
description: >-
  Board-only financial and strategic assistant. Answers Direction-level
  financial and strategic questions with access to a large tool set
  explicitly excluding technical tools and the technical RAG corpora.
provenance:
  maintainer: Zuno Demo architecture team
  repository: zuno-demo
verification:
  status: unverified
freshness:
  last_reviewed: "2026-08-15"
sources: []
zuno:
  name: cognos
  status: placeholder
  tasks:
    - coming-soon
  model:
    preferred_classification: C3
    notes: >-
      Placeholder pending a future build (ADR-0349 defines only the
      identity footprint); C3 anticipated because Direction-level
      financial and strategic material is local-model-only by nature.
  access:
    # ADR-0040: agent entitlement group, orthogonal to the `board`
    # business role that will govern tool/data permissions inside Cognos
    # (ADR-0349 §6 - audience is Direction only).
    groups:
      - agent_cognos
  ui:
    displayName: Cognos
    tileDescription: Board financial and strategic assistant - coming soon.
    color: "#4A148C"
    icon: chart-line
---

# Cognos

ADR-0349 §6: `status` is `placeholder` - this bundle, the
`cognos-frontend` Keycloak client, the `agent_cognos` entitlement group
and this portal tile are the only things that exist for Cognos today
(the original placeholder pattern comage/advantage/finage/arkos each
started from). No dedicated namespace is reserved (ADR-0329): a future
active Cognos deployment would run in the shared `zuno-ai-run`
namespace, CR-managed via the AIAgent operator (ADR-0327/ADR-0308) like
every agent onboarded since WP-38.

`tasks/coming-soon.md` describes the intended build - Direction-level
financial and strategic Q&A over RAG/MCP capabilities that explicitly
exclude the technical tools and technical RAG corpora - kept here so
onboarding Cognos later is primarily a `status: active` flip plus real
task implementation through the ADR-0307 template workflow
(`platform/templates/agent/`), not a redesign.

<!-- BEGIN GENERATED AUTHORIZATION MATRIX (ADR-0503) - do not edit; regenerate with: python3 platform/okf/generate_authorization_matrix.py -->

## Authorization matrix

Generated per ADR-0503 from this bundle's frontmatter, `policies/tools/tool-policy.yaml` and `policies/knowledge/knowledge-policy.yaml` — the enforced intersection (ADR-0011/ADR-0203) restated for review, never read at runtime. Entitlement (ADR-0040): `agent_cognos`; model classification ceiling (ADR-0021): `C3`; status: `placeholder`.

No capabilities declared: every task's `allowed_tools`/`allowed_knowledge` is empty, so this agent can invoke no tool and retrieve from no knowledge domain regardless of caller groups (the honest Stage-1 zero-capability state, ADR-0502).

<!-- END GENERATED AUTHORIZATION MATRIX -->
