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

<!-- BEGIN GENERATED AUTHORIZATION MATRIX (ADR-0503) - do not edit; regenerate with: python3 platform/okf/generate_authorization_matrix.py -->

## Authorization matrix

Generated per ADR-0503 from this bundle's frontmatter, `policies/tools/tool-policy.yaml`, `policies/knowledge/knowledge-policy.yaml`, `platform/ai-gateway/provider-routing.yaml` and `policies/model-routing/model-routing-policy.yaml` — the enforced intersection (ADR-0011/ADR-0203) restated for review, never read at runtime. Entitlement (ADR-0040): `agent_naveo`; model classification ceiling (ADR-0021): `C1`; status: `placeholder`.

| Task (FOR WHAT) | Resource (WHAT) | Kind | Capability / server | Min class | Business roles (WHO) | Ext-model context | Quota | Policy source |
|---|---|---|---|---|---|---|---|---|
| `answer-onboarding-question` (primary; prompt: `prompts/answer-onboarding-question.md`) | `search_confluence` (live-read) | tool | `confluence.page.search` @ confluence | C2 | consultant, board, cdp, lightspeed_readonly | blocked | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `search_confluence` |
| `answer-onboarding-question` (primary; prompt: `prompts/answer-onboarding-question.md`) | `web_search` | tool | `web.page.search` @ web-search | C1 | sales, consultant, adv, finance, board | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `web_search` |
| `answer-onboarding-question` (primary; prompt: `prompts/answer-onboarding-question.md`) | `list_drive_files` | tool | `drive.document.search` @ google-workspace | C1 | consultant, board, cdp, sales, adv, finance | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `list_drive_files` |
| `answer-onboarding-question` (primary; prompt: `prompts/answer-onboarding-question.md`) | `knowledge.tech` | knowledge | — | — | consultant, board, cdp | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.tech` |
| `answer-onboarding-question` (primary; prompt: `prompts/answer-onboarding-question.md`) | `knowledge.project` | knowledge | — | — | consultant, board, sales, adv, finance, cdp | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.project` |

### Model routing

Effective per-task model chain (ADR-0021/ADR-0303/ADR-0412), resolved from `platform/ai-gateway/provider-routing.yaml`'s classification eligibility reordered by this `(agent, task)`'s `policies/model-routing/model-routing-policy.yaml` preference — the first entry is the reference model, the rest are fallback alternatives, in try order. The reference model is annotated with the model id it actually serves and that model's architectural role (`default`, `quality`, `reasoning`, `specialized`, `reasoning-external`, `code`, `general-external`); `provider-routing.yaml`'s `role` key is the authority for both, and every model reachable through the fallback chain is named in the **Available models** rollup below the table.

| Task | Classification ceiling | Reference model | Fallback chain | Adapter | Policy source |
|---|---|---|---|---|---|
| `answer-onboarding-question` (primary; prompt: `prompts/answer-onboarding-question.md`) | `C1` | `local-qwen35-maas` → `qwen3.5-9b` (default) | `local-qwen35`, `local-gpt-oss-maas`, `local-gpt-oss`, `local-maas`, `local`, `local-wesh-maas`, `local-wesh`, `openai`, `gemini`, `anthropic`, `mistral`, `mistral-codestral`, `ovhcloud-gpt-oss-120b` | — | `policies/model-routing/model-routing-policy.yaml` |

**Available models** (ADR-0419, generated): the union of every model reachable by any task or prompt slot above, at any classification, each with the model id it serves and that model's role - `local-maas` → `qwen3.6-27b-instruct` (quality), `local` → `qwen3.6-27b-instruct` (quality), `local-gpt-oss-maas` → `gpt-oss-20b` (reasoning), `local-gpt-oss` → `gpt-oss-20b` (reasoning), `local-wesh-maas` → `qwen3.5-9b-wesh` (specialized), `local-wesh` → `qwen3.5-9b-wesh` (specialized), `local-qwen35-maas` → `qwen3.5-9b` (default), `local-qwen35` → `qwen3.5-9b` (default), `openai` → `gpt-4o-mini` (general-external), `gemini` → `gemini-1.5-pro` (general-external), `anthropic` → `claude-3-5-sonnet-latest` (general-external), `mistral` → `mistral-large-latest` (general-external), `mistral-codestral` → `codestral-latest` (code), `ovhcloud-gpt-oss-120b` → `gpt-oss-120b` (reasoning-external).

<!-- END GENERATED AUTHORIZATION MATRIX -->
