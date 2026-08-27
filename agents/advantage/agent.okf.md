---
okf_version: v0.2
type: agent
title: Advantage
description: >-
  Sales administration assistant. Surfaces new business whose client
  purchase order has just been received and produces monthly in-progress
  sales reporting, drawing on indexed ADV/project knowledge - never
  live Salesforce data (ADR-0326: explicit cross-domain boundary, not
  implicit inheritance from Comage). ADR-0218 removed `knowledge.adv`'s
  only ingestion adapter, so that domain has no source today; choosing a
  replacement is an open decision for this slice.
provenance:
  maintainer: Zuno Demo architecture team
  repository: zuno-demo
verification:
  status: unverified
freshness:
  last_reviewed: "2026-08-05"
sources:
  - "knowledge.adv (no ingestion adapter since ADR-0218; source undecided)"
  - "knowledge.project"
zuno:
  name: advantage
  status: placeholder
  graph_shape: retrieve_reason_respond
  primary_task: answer-project-question
  tasks:
    - answer-project-question
    - identify-new-business-with-po
    - monthly-sales-report
    - check-my-drive-and-mail
  model:
    preferred_classification: C2
    notes: >-
      Placeholder pending the live acceptance gate; C2 matches
      `knowledge.adv`'s own classification
      (policies/data-classification/classification.yaml's `sales-data`
      domain covers ADV business content too, ADR-0034).
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

ADR-0326 (WP-35): Advantage's real OKF task bundle, graph shape and
deployment surface are now merged - `status` stays `placeholder` until
the operator confirms the live acceptance gate passes (WP-35's own
Status-updates section; ADR-0326's "moves placeholder -> active only
after the full common completion pattern passes"), so the portal keeps
rendering "coming soon" and Agent Runtime's generic dispatch keeps
404ing `/v1/agents/advantage/chat` until that flip happens. No dedicated
namespace is reserved (ADR-0329, supersedes ADR-0023): Advantage's
frontend/BFF deploy into the shared `zuno-ai-run` namespace, same as
Tekos/Arkos/Comage.

`zuno.graph_shape: retrieve_reason_respond` (ADR-0342) names the exact
same LangGraph workflow module Tekos's and Comage's chat turns execute -
proving a THIRD agent reuses this shape with zero code change.
`answer-project-question` (`tasks/answer-project-question.md`) is the one
live-routed task: it reads `knowledge.adv` + `knowledge.project`, and
declares no `live_read_tool` at all, and since ADR-0218 dropped
`fetch-aramis` there is no batch adapter behind `knowledge.adv` either -
neither an indexed source nor a live adv capability exists today.
Advantage's other three declared tasks
(`identify-new-business-with-po`, `monthly-sales-report`,
`check-my-drive-and-mail`) are v1-scope catalog entries with no dedicated
route yet, matching Tekos's/Comage's own catalog-only tasks pattern.

**ADR-0326's signature proof for this slice**: no task above ever
declares Comage's own current-sales knowledge domain in
`allowed_knowledge`, or any live-CRM/legacy-SXA capability in
`allowed_tools` - Advantage proves the cross-domain authorization
boundary by explicit omission from its own OKF declaration (the
ADR-0011/ADR-0203 agent_declaration factor), never by a runtime filter
that could silently be widened later. Any cross-domain commercial access
Advantage might need in a future iteration must be added here explicitly
and policy-controlled, never inherited from Comage.

Advantage has no agent-level `zuno.allowed_knowledge` field either
(ADR-0203), for the same reason Tekos/Arkos/Comage don't: its knowledge
ceiling is the union of every task's own `zuno.allowed_knowledge` -
today `[knowledge.adv, knowledge.project]`.

Access group is `agent_advantage` (ADR-0040 entitlement dimension,
orthogonal to the `adv` business role that governs tool/data permissions
inside Advantage once active - see `policies/tools/tool-policy.yaml`'s
Drive/Gmail entries and `policies/knowledge/knowledge-policy.yaml`'s
`knowledge.adv`/`knowledge.project` entries).

<!-- BEGIN GENERATED AUTHORIZATION MATRIX (ADR-0503) - do not edit; regenerate with: python3 platform/okf/generate_authorization_matrix.py -->

## Authorization matrix

Generated per ADR-0503 from this bundle's frontmatter, `policies/tools/tool-policy.yaml`, `policies/knowledge/knowledge-policy.yaml`, `platform/ai-gateway/provider-routing.yaml` and `policies/model-routing/model-routing-policy.yaml` — the enforced intersection (ADR-0011/ADR-0203) restated for review, never read at runtime. Entitlement (ADR-0040): `agent_advantage`; model classification ceiling (ADR-0021): `C2`; status: `placeholder`.

| Task (FOR WHAT) | Resource (WHAT) | Kind | Capability / server | Min class | Business roles (WHO) | Ext-model context | Quota | Policy source |
|---|---|---|---|---|---|---|---|---|
| `answer-project-question` (primary; prompt: `prompts/answer-project-question.md`) | `web_search` | tool | `web.page.search` @ web-search | C1 | sales, consultant, adv, finance, board | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `web_search` |
| `answer-project-question` (primary; prompt: `prompts/answer-project-question.md`) | `image.generation.create` | tool | `image.generation.create` @ image-gen | C2 | consultant, adv, sales, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `generate_image` |
| `answer-project-question` (primary; prompt: `prompts/answer-project-question.md`) | `knowledge.adv` | knowledge | — | C2 | adv, board, cdp, finance | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.adv` |
| `answer-project-question` (primary; prompt: `prompts/answer-project-question.md`) | `knowledge.project` | knowledge | — | — | consultant, board, sales, adv, finance, cdp | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.project` |
| `answer-project-question` (primary; prompt: `prompts/answer-project-question.md`) | `knowledge.sxa-legacy` | knowledge | — | C3 | sales, board, adv, finance | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.sxa-legacy` |
| `identify-new-business-with-po` | `knowledge.adv` | knowledge | — | C2 | adv, board, cdp, finance | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.adv` |
| `monthly-sales-report` | `knowledge.adv` | knowledge | — | C2 | adv, board, cdp, finance | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.adv` |
| `check-my-drive-and-mail` | `list_drive_files` | tool | `drive.document.search` @ google-workspace | C1 | consultant, board, cdp, sales, adv, finance | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `list_drive_files` |
| `check-my-drive-and-mail` | `read_gmail` | tool | `gmail.message.read` @ google-workspace | C1 | consultant, board, cdp, sales, adv, finance | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `read_gmail` |

### Model routing

Effective per-task model chain (ADR-0021/ADR-0303/ADR-0412), resolved from `platform/ai-gateway/provider-routing.yaml`'s classification eligibility reordered by this `(agent, task)`'s `policies/model-routing/model-routing-policy.yaml` preference — the first entry is the reference model, the rest are fallback alternatives, in try order.

| Task | Classification ceiling | Reference model | Fallback chain | Adapter | Policy source |
|---|---|---|---|---|---|
| `answer-project-question` (primary; prompt: `prompts/answer-project-question.md`) | `C2` | `local-gpt-oss-maas` | `local-gpt-oss`, `local-maas`, `local`, `local-wesh-maas`, `local-wesh`, `local-qwen35-maas`, `local-qwen35`, `openai`, `anthropic`, `mistral-codestral`, `ovhcloud-gpt-oss-120b` | — | `policies/model-routing/model-routing-policy.yaml` |
| `identify-new-business-with-po` | `C2` | `local-gpt-oss-maas` | `local-gpt-oss`, `local-maas`, `local`, `local-wesh-maas`, `local-wesh`, `local-qwen35-maas`, `local-qwen35`, `openai`, `anthropic`, `mistral-codestral`, `ovhcloud-gpt-oss-120b` | — | `policies/model-routing/model-routing-policy.yaml` |
| `monthly-sales-report` | `C2` | `local-gpt-oss-maas` | `local-gpt-oss`, `local-maas`, `local`, `local-wesh-maas`, `local-wesh`, `local-qwen35-maas`, `local-qwen35`, `openai`, `anthropic`, `mistral-codestral`, `ovhcloud-gpt-oss-120b` | — | `policies/model-routing/model-routing-policy.yaml` |
| `check-my-drive-and-mail` | `C2` | `local-maas` | `local`, `local-gpt-oss-maas`, `local-gpt-oss`, `local-wesh-maas`, `local-wesh`, `local-qwen35-maas`, `local-qwen35`, `openai`, `anthropic`, `mistral-codestral`, `ovhcloud-gpt-oss-120b` | — | `policies/model-routing/model-routing-policy.yaml` |

**Available models** (ADR-0419, generated): the union of every model reachable by any task or prompt slot above, at any classification - `local-maas`, `local`, `local-gpt-oss-maas`, `local-gpt-oss`, `local-wesh-maas`, `local-wesh`, `local-qwen35-maas`, `local-qwen35`, `openai`, `anthropic`, `mistral-codestral`, `ovhcloud-gpt-oss-120b`.

<!-- END GENERATED AUTHORIZATION MATRIX -->
