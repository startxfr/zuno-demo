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
  primary_task: draft-architecture-testimonial
  tasks:
    - draft-architecture-testimonial
    - write-code
  memory:
    # ADR-0215: Arkos is C3/local-only (see model.preferred_classification
    # below), so its history-carrying model calls route to gpt-oss-20b
    # rather than qwen2.5-7b-instruct - a much larger context window
    # (32768 vs 8192, see gitops/charts/models/values.yaml), so its
    # history budget can be generous rather than riding the tighter
    # qwen-sized default (app/registry.py's HISTORY_TOKEN_BUDGET, 1800).
    history:
      enabled: true
      max_turns: 6
      token_budget: 6000
  model:
    preferred_classification: C3
    notes: >-
      Placeholder pending v1 build; C3 anticipated because sovereign-marked
      DAT workflows are local-model-only per MEMORY.md section 5.
  access:
    # ADR-0040: agent entitlement group, orthogonal to the `consultant`
    # business role that governs tool/data permissions inside Arkos
    # (ADR-0349: architects are the consultant tier - the
    # confluence-archi-* skill subgroups live under /consultant - so
    # Arkos's audience moved from board to consultant; `board` means
    # Direction only).
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
to the `consultant` business role that governs tool/data permissions
inside Arkos once active - see `policies/tools/tool-policy.yaml`'s
`drive.document.*`/`confluence.page.*` entries, both of which list
`consultant`). ADR-0349 moved Arkos's audience from board to the
consultant architect tier (the `confluence-archi-*` skill subgroups live
under `/consultant`; `board` means Direction only) - DATs are still
*reviewed* at board level as a business process, but the role gating an
already-entitled Arkos session is `consultant`, matching every other
agent's ADR-0040 dimension split.

<!-- BEGIN GENERATED AUTHORIZATION MATRIX (ADR-0503) - do not edit; regenerate with: python3 platform/okf/generate_authorization_matrix.py -->

## Authorization matrix

Generated per ADR-0503 from this bundle's frontmatter, `policies/tools/tool-policy.yaml`, `policies/knowledge/knowledge-policy.yaml`, `platform/ai-gateway/provider-routing.yaml` and `policies/model-routing/model-routing-policy.yaml` — the enforced intersection (ADR-0011/ADR-0203) restated for review, never read at runtime. Entitlement (ADR-0040): `agent_arkos`; model classification ceiling (ADR-0021): `C3`; status: `placeholder`.

| Task (FOR WHAT) | Resource (WHAT) | Kind | Capability / server | Min class | Business roles (WHO) | Ext-model context | Quota | Policy source |
|---|---|---|---|---|---|---|---|---|
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `confluence.page.read` | tool | `confluence.page.read` @ confluence | C2 | consultant, board, cdp | blocked | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `confluence.page.read` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `confluence.page.search` | tool | `confluence.page.search` @ confluence | C2 | consultant, board, cdp | blocked | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `search_confluence` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `drive.document.create` | tool | `drive.document.create` @ google-workspace | C1 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `drive.document.create` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `drive.document.update` | tool | `drive.document.update` @ google-workspace | C1 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `drive.document.update` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `git.repository.read` | tool | `git.repository.read` @ git-forge | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `git.repository.read` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `git.repository.list` | tool | `git.repository.list` @ git-forge | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `git.repository.list` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `git.repository.private.read` | tool | `git.repository.private.read` @ git-forge | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `git.repository.private.read` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `git.repository.private.list` | tool | `git.repository.private.list` @ git-forge | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `git.repository.private.list` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `git.file.write` | tool | `git.file.write` @ git-forge | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `git.file.write` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `git.repository.create` | tool | `git.repository.create` @ git-forge | C2 | consultant, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `git.repository.create` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `image.generation.create` | tool | `image.generation.create` @ image-gen | C2 | consultant, adv, sales, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `generate_image` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `knowledge.tech` | knowledge | — | — | consultant, board, cdp | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.tech` |
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `knowledge.project` | knowledge | — | — | consultant, board, sales, adv, finance, cdp | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.project` |

### Model routing

Effective per-task model chain (ADR-0021/ADR-0303/ADR-0412), resolved from `platform/ai-gateway/provider-routing.yaml`'s classification eligibility reordered by this `(agent, task)`'s `policies/model-routing/model-routing-policy.yaml` preference — the first entry is the reference model, the rest are fallback alternatives, in try order.

| Task | Classification ceiling | Reference model | Fallback chain | Adapter | Policy source |
|---|---|---|---|---|---|
| `draft-architecture-testimonial` (primary; prompt: `prompts/draft-architecture-testimonial.md`) | `C3` | `local-gpt-oss` | `local` | — | `policies/model-routing/model-routing-policy.yaml` |
| `write-code` | `C3` | (none eligible) | — | — | `policies/model-routing/model-routing-policy.yaml` |

<!-- END GENERATED AUTHORIZATION MATRIX -->
