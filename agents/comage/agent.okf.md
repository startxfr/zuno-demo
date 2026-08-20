---
okf_version: v0.2
type: agent
title: Comage
description: >-
  Sales assistant. Answers deal-status questions grounded in indexed and
  live Salesforce data, updates opportunities, compares against historical
  legacy SXA figures, and checks the user's own Drive/Gmail for
  account-relevant material.
provenance:
  maintainer: Zuno Demo architecture team
  repository: zuno-demo
verification:
  status: unverified
freshness:
  last_reviewed: "2026-08-05"
sources:
  - "knowledge.sales (asynchronously ingested from Salesforce, WP-22)"
  - "knowledge.sxa-legacy (imported legacy SXA snapshot)"
  - salesforce
zuno:
  name: comage
  status: placeholder
  graph_shape: retrieve_reason_respond
  primary_task: check-deal-status
  tasks:
    - check-deal-status
    - update-opportunity-status
    - compare-historical-deals
    - check-my-drive-and-mail
  model:
    preferred_classification: C2
    notes: >-
      Placeholder pending the live acceptance gate; C2 matches
      `knowledge.sales`/`salesforce.*`'s own classification
      (policies/data-classification/classification.yaml's `sales-data`
      domain) - escalates to C3 whenever a turn touches
      `knowledge.sxa-legacy` (ADR-0034).
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

ADR-0326 (WP-33): Comage's real OKF task bundle, graph shape and
deployment surface are now merged - `status` stays `placeholder` until the
operator confirms the live acceptance gate passes (WP-33's own Status-
updates section; ADR-0326's "moves placeholder -> active only after the
full common completion pattern passes"), so the portal keeps rendering
"coming soon" and Agent Runtime's generic dispatch keeps 404ing
`/v1/agents/comage/chat` until that flip happens. No dedicated namespace
is reserved (ADR-0329, supersedes ADR-0023): Comage's frontend/BFF deploy
into the shared `zuno-ai-run` namespace, same as Tekos/Arkos.

`zuno.graph_shape: retrieve_reason_respond` (ADR-0342) names the exact
same LangGraph workflow module Tekos's chat turns execute - the strongest
available proof that WP-30's graph-shape mechanism is genuine config-only
reuse, not topology duplication (ADR-0326's "Comage proves the
indexed-read/live-action pattern"). `check-deal-status`
(`tasks/check-deal-status.md`) is the one live-routed task: it prefers
`knowledge.sales` for ordinary reads and triggers a live
`salesforce.opportunity.read` call (`zuno.live_read_tool`) whenever the
question needs a mutable field's current value. Comage's other three
declared tasks (`update-opportunity-status`, `compare-historical-deals`,
`check-my-drive-and-mail`) are v1-scope catalog entries with no dedicated
route yet, matching Tekos's own `find-relevant-docs`/`check-my-drive-docs`
pattern - declared so their `allowed_tools`/`allowed_knowledge` already
narrow Comage's overall ceiling correctly.

Comage has no agent-level `zuno.allowed_knowledge` field either
(ADR-0203), for the same reason Tekos/Arkos don't: its knowledge ceiling
is the union of every task's own `zuno.allowed_knowledge` - today
`[knowledge.sales, knowledge.project, knowledge.sxa-legacy]`.

Access group is `agent_comage` (ADR-0040 entitlement dimension, orthogonal
to the `sales` business role that governs tool/data permissions inside
Comage once active - see `policies/tools/tool-policy.yaml`'s
`salesforce.opportunity.*`/`sxa.*` entries).

<!-- BEGIN GENERATED AUTHORIZATION MATRIX (ADR-0503) - do not edit; regenerate with: python3 platform/okf/generate_authorization_matrix.py -->

## Authorization matrix

Generated per ADR-0503 from this bundle's frontmatter, `policies/tools/tool-policy.yaml`, `policies/knowledge/knowledge-policy.yaml`, `platform/ai-gateway/provider-routing.yaml` and `policies/model-routing/model-routing-policy.yaml` — the enforced intersection (ADR-0011/ADR-0203) restated for review, never read at runtime. Entitlement (ADR-0040): `agent_comage`; model classification ceiling (ADR-0021): `C2`; status: `placeholder`.

| Task (FOR WHAT) | Resource (WHAT) | Kind | Capability / server | Min class | Business roles (WHO) | Ext-model context | Quota | Policy source |
|---|---|---|---|---|---|---|---|---|
| `check-deal-status` (primary; prompt: `prompts/check-deal-status.md`) | `salesforce.opportunity.read` (live-read) | tool | `salesforce.opportunity.read` @ salesforce | C2 | sales, board | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `salesforce.opportunity.read` |
| `check-deal-status` (primary; prompt: `prompts/check-deal-status.md`) | `web_search` | tool | `web.page.search` @ web-search | C1 | sales, consultant, adv, finance, board | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `web_search` |
| `check-deal-status` (primary; prompt: `prompts/check-deal-status.md`) | `image.generation.create` | tool | `image.generation.create` @ image-gen | C2 | consultant, adv, sales, board, cdp | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `generate_image` |
| `check-deal-status` (primary; prompt: `prompts/check-deal-status.md`) | `knowledge.sales` | knowledge | — | C2 | sales, adv, board, cdp, finance | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.sales` |
| `check-deal-status` (primary; prompt: `prompts/check-deal-status.md`) | `knowledge.project` | knowledge | — | — | consultant, board, sales, adv, finance, cdp | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.project` |
| `update-opportunity-status` | `salesforce.opportunity.update` | tool | `salesforce.opportunity.update` @ salesforce | C2 | sales, board | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `salesforce.opportunity.update` |
| `compare-historical-deals` | `sxa.opportunity.search` | tool | `sxa.opportunity.search` @ sales-db | C2 | sales, adv, board, finance | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `list_open_opportunities` |
| `compare-historical-deals` | `sxa.aggregate.revenue-by-year` | tool | `sxa.aggregate.revenue-by-year` @ sales-db | C3 | sales, board, finance | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `aggregate_revenue_by_year` |
| `compare-historical-deals` | `knowledge.sxa-legacy` | knowledge | — | C3 | sales, board | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.sxa-legacy` |
| `check-my-drive-and-mail` | `list_drive_files` | tool | `drive.document.search` @ google-workspace | C1 | consultant, board, cdp, sales, adv, finance | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `list_drive_files` |
| `check-my-drive-and-mail` | `read_gmail` | tool | `gmail.message.read` @ google-workspace | C1 | consultant, board, cdp, sales, adv, finance | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `read_gmail` |

### Model routing

Effective per-task model chain (ADR-0021/ADR-0303/ADR-0412), resolved from `platform/ai-gateway/provider-routing.yaml`'s classification eligibility reordered by this `(agent, task)`'s `policies/model-routing/model-routing-policy.yaml` preference — the first entry is the reference model, the rest are fallback alternatives, in try order.

| Task | Classification ceiling | Reference model | Fallback chain | Adapter | Policy source |
|---|---|---|---|---|---|
| `check-deal-status` (primary; prompt: `prompts/check-deal-status.md`) | `C2` | `local` | `local-gpt-oss`, `openai`, `anthropic`, `mistral-codestral`, `ovhcloud-gpt-oss-120b` | — | `policies/model-routing/model-routing-policy.yaml` |
| `update-opportunity-status` | `C2` | `local` | `local-gpt-oss`, `openai`, `anthropic`, `mistral-codestral`, `ovhcloud-gpt-oss-120b` | — | `policies/model-routing/model-routing-policy.yaml` |
| `compare-historical-deals` | `C2` | `local-gpt-oss` | `local`, `openai`, `anthropic`, `mistral-codestral`, `ovhcloud-gpt-oss-120b` | — | `policies/model-routing/model-routing-policy.yaml` |
| `check-my-drive-and-mail` | `C2` | `local` | `local-gpt-oss`, `openai`, `anthropic`, `mistral-codestral`, `ovhcloud-gpt-oss-120b` | — | `policies/model-routing/model-routing-policy.yaml` |

<!-- END GENERATED AUTHORIZATION MATRIX -->
