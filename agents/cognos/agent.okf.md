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
    - review-historical-commercial-data
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

`tasks/review-historical-commercial-data.md` is this bundle's first real
(non-`coming-soon`) task - its `allowed_knowledge: [knowledge.sxa-legacy]`
grant is declared and policy-backed but inert while `status` stays
`placeholder` (see that task file's own note and `NEXT_STEPS.md`). It
originally named ADR-0217's second SXA domain; ADR-0219 retired it and the
grant moved to the surviving `knowledge.sxa-legacy`, which also lists
`board`, so it remained valid without a policy edit.

<!-- BEGIN GENERATED AUTHORIZATION MATRIX (ADR-0503) - do not edit; regenerate with: python3 platform/okf/generate_authorization_matrix.py -->

## Authorization matrix

Generated per ADR-0503 from this bundle's frontmatter, `policies/tools/tool-policy.yaml`, `policies/knowledge/knowledge-policy.yaml`, `platform/ai-gateway/provider-routing.yaml` and `policies/model-routing/model-routing-policy.yaml` — the enforced intersection (ADR-0011/ADR-0203) restated for review, never read at runtime. Entitlement (ADR-0040): `agent_cognos`; model classification ceiling (ADR-0021): `C3`; status: `placeholder`.

| Task (FOR WHAT) | Resource (WHAT) | Kind | Capability / server | Min class | Business roles (WHO) | Ext-model context | Quota | Policy source |
|---|---|---|---|---|---|---|---|---|
| `review-historical-commercial-data` | `knowledge.sxa-legacy` | knowledge | — | C3 | sales, board, adv, finance | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.sxa-legacy` |

### Model routing

Effective per-task model chain (ADR-0021/ADR-0303/ADR-0412), resolved from `platform/ai-gateway/provider-routing.yaml`'s classification eligibility reordered by this `(agent, task)`'s `policies/model-routing/model-routing-policy.yaml` preference — the first entry is the reference model, the rest are fallback alternatives, in try order.

| Task | Classification ceiling | Reference model | Fallback chain | Adapter | Policy source |
|---|---|---|---|---|---|
| `coming-soon` | `C3` | `local-gpt-oss-maas` | `local-gpt-oss`, `local-maas`, `local` | — | `policies/model-routing/model-routing-policy.yaml` |
| `review-historical-commercial-data` | `C3` | `local-maas` | `local`, `local-gpt-oss-maas`, `local-gpt-oss` | — | `policies/model-routing/model-routing-policy.yaml` |

**Available models** (ADR-0419, generated): the union of every model reachable by any task or prompt slot above, at any classification - `local-maas`, `local`, `local-gpt-oss-maas`, `local-gpt-oss`.

<!-- END GENERATED AUTHORIZATION MATRIX -->
