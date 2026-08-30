---
okf_version: v0.2
type: agent
title: Finage
description: >-
  Finance assistant. Identifies business ready to invoice and produces
  monthly invoice reporting, drawing on legacy SXA revenue/billing
  history via retrieval (knowledge.sxa-legacy, ADR-0219 - no deterministic
  query capabilities remain) and durable project memory - never live
  Salesforce or ADV/project-delivery data (ADR-0326: strictly
  finance-scoped, no implicit inheritance from Comage/Advantage).
provenance:
  maintainer: Zuno Demo architecture team
  repository: zuno-demo
verification:
  status: unverified
freshness:
  last_reviewed: "2026-08-05"
sources:
  - "knowledge.project"
  - "knowledge.sxa-legacy (pre-2021 commercial record, retrieval only, ADR-0219)"
zuno:
  name: finage
  status: placeholder
  graph_shape: retrieve_reason_respond
  primary_task: answer-finance-question
  tasks:
    - answer-finance-question
    - identify-business-ready-to-invoice
    - monthly-invoice-report
    - check-my-drive-and-mail
  model:
    preferred_classification: C2
    local_only: true
    notes: >-
      Placeholder pending the live acceptance gate; C2 default.
      `knowledge.sxa-legacy` (retrieval only, no deterministic
      aggregation/lookup capabilities since ADR-0219 retired them) was
      reclassified from C3 to C2 (ADR-0206 Status update, 2026-08-30), so a
      turn touching it no longer escalates above C2 either. ADR-0416:
      `local_only: true` makes Finage local-model-only
      unconditionally, at every classification including C1 - finance
      material never leaves the cluster, full stop, rather than riding
      the standard C2 restricted-SaaS-allowlist default every other C2
      agent gets.
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

ADR-0326 (WP-36): Finage's real OKF task bundle, graph shape and
deployment surface are now merged - `status` stays `placeholder` until
the operator confirms the live acceptance gate passes (WP-36's own
Status-updates section; ADR-0326's "moves placeholder -> active only
after the full common completion pattern passes"), so the portal keeps
rendering "coming soon" and Agent Runtime's generic dispatch keeps
404ing `/v1/agents/finage/chat` until that flip happens. No dedicated
namespace is reserved (ADR-0329, supersedes ADR-0023): Finage's
frontend/BFF deploy into the shared `zuno-ai-run` namespace, same as
every other agent.

`zuno.graph_shape: retrieve_reason_respond` (ADR-0342) names the exact
same LangGraph workflow module Tekos's, Comage's and Advantage's chat
turns execute - proving a FOURTH agent reuses this shape with zero code
change. `answer-finance-question` (`tasks/answer-finance-question.md`) is
the one live-routed task: it declares no `live_read_tool` at all, unlike
Comage's/Arkos's live-read tools - every deterministic legacy SXA
capability Finage's other tasks declare needs structured numeric
arguments (year, customer_id, ...), not a free-text query, so it does not
fit the generic freshness-triggered live-read mechanism and stays
declared-but-not-live-routed (v1 scope) instead of forcing a mismatched
integration.

**Documented gap (WP-36's own brief anticipates this)**: no
finance-specific RAG knowledge domain exists in this repository. Rather
than inventing one, Finage's tasks declare `knowledge.project` (cross-agent
project memory) and `knowledge.sxa-legacy` (the pre-2021 commercial record)
for retrieval. ADR-0219 widened that domain's `allowed_groups` to include
`finance`, so the boundary WP-36 originally had to honor no longer applies.

What remains open, and is now the sharper gap, is the *deterministic* side:
Finage has no exact-figure capability at all. It was built on the `sxa.*`
capabilities that ADR-0219 removed, and they are not coming back through
this route - SXA is a closed pre-2021 record with no live billing system
behind it, so nothing here can be authoritative about a current invoice.
Every number Finage reports is retrieved and attributed, never computed.

**ADR-0326's signature proof for this slice**: no task above ever
declares the current-sales or ADV/project-delivery knowledge domains in
`allowed_knowledge`, or any live-Salesforce/Aramis capability in
`allowed_tools` - Finage proves least-privilege, finance-scoped access by
explicit omission from its own OKF declaration (the ADR-0011/ADR-0203
agent_declaration factor), never a runtime filter.

Finage has no agent-level `zuno.allowed_knowledge` field either
(ADR-0203), for the same reason every other agent doesn't: its knowledge
ceiling is the union of every task's own `zuno.allowed_knowledge` - today
just `[knowledge.project]`.

Access group is `agent_finage` (ADR-0040 entitlement dimension,
orthogonal to the `finance` business role that governs tool/data
permissions inside Finage once active - see
`policies/tools/tool-policy.yaml`'s Drive/Gmail entries).

<!-- BEGIN GENERATED AUTHORIZATION MATRIX (ADR-0503) - do not edit; regenerate with: python3 platform/okf/generate_authorization_matrix.py -->

## Authorization matrix

Generated per ADR-0503 from this bundle's frontmatter, `policies/tools/tool-policy.yaml`, `policies/knowledge/knowledge-policy.yaml`, `platform/ai-gateway/provider-routing.yaml` and `policies/model-routing/model-routing-policy.yaml` — the enforced intersection (ADR-0011/ADR-0203) restated for review, never read at runtime. Entitlement (ADR-0040): `agent_finage`; model classification ceiling (ADR-0021): `C2`; status: `placeholder`; local-only (ADR-0416): `true`.

| Task (FOR WHAT) | Resource (WHAT) | Kind | Capability / server | Min class | Business roles (WHO) | Ext-model context | Quota | Policy source |
|---|---|---|---|---|---|---|---|---|
| `answer-finance-question` (primary; prompt: `prompts/answer-finance-question.md`) | `web_search` | tool | `web.page.search` @ web-search | C1 | sales, consultant, adv, finance, board | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `web_search` |
| `answer-finance-question` (primary; prompt: `prompts/answer-finance-question.md`) | `knowledge.project` | knowledge | — | — | consultant, board, sales, adv, finance, cdp | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.project` |
| `answer-finance-question` (primary; prompt: `prompts/answer-finance-question.md`) | `knowledge.sxa-legacy` | knowledge | — | C2 | sales, board, adv, finance | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.sxa-legacy` |
| `identify-business-ready-to-invoice` (project-required; prompt: `prompts/identify-business-ready-to-invoice.md`) | `salesforce.opportunity.read` | tool | `salesforce.opportunity.read` @ salesforce | C2 | sales, board | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `salesforce.opportunity.read` |
| `identify-business-ready-to-invoice` (project-required; prompt: `prompts/identify-business-ready-to-invoice.md`) | `knowledge.project` | knowledge | — | — | consultant, board, sales, adv, finance, cdp | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.project` |
| `identify-business-ready-to-invoice` (project-required; prompt: `prompts/identify-business-ready-to-invoice.md`) | `knowledge.sxa-legacy` | knowledge | — | C2 | sales, board, adv, finance | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.sxa-legacy` |
| `monthly-invoice-report` (project-required; prompt: `prompts/monthly-invoice-report.md`) | `salesforce.opportunity.read` | tool | `salesforce.opportunity.read` @ salesforce | C2 | sales, board | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `salesforce.opportunity.read` |
| `monthly-invoice-report` (project-required; prompt: `prompts/monthly-invoice-report.md`) | `knowledge.project` | knowledge | — | — | consultant, board, sales, adv, finance, cdp | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.project` |
| `monthly-invoice-report` (project-required; prompt: `prompts/monthly-invoice-report.md`) | `knowledge.sxa-legacy` | knowledge | — | C2 | sales, board, adv, finance | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.sxa-legacy` |
| `check-my-drive-and-mail` | `list_drive_files` | tool | `drive.document.search` @ google-workspace | C1 | consultant, board, cdp, sales, adv, finance | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `list_drive_files` |
| `check-my-drive-and-mail` | `read_gmail` | tool | `gmail.message.read` @ google-workspace | C1 | consultant, board, cdp, sales, adv, finance | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `read_gmail` |

### Model routing

Effective per-task model chain (ADR-0021/ADR-0303/ADR-0412), resolved from `platform/ai-gateway/provider-routing.yaml`'s classification eligibility reordered by this `(agent, task)`'s `policies/model-routing/model-routing-policy.yaml` preference — the first entry is the reference model, the rest are fallback alternatives, in try order.

| Task | Classification ceiling | Reference model | Fallback chain | Adapter | Policy source |
|---|---|---|---|---|---|
| `answer-finance-question` (primary; prompt: `prompts/answer-finance-question.md`) | `C2` | `local-qwen35-maas` | `local-qwen35`, `local-gpt-oss-maas`, `local-gpt-oss`, `local-maas`, `local`, `local-wesh-maas`, `local-wesh` | — | `policies/model-routing/model-routing-policy.yaml` |
| `identify-business-ready-to-invoice` (project-required; prompt: `prompts/identify-business-ready-to-invoice.md`) | `C2` | `local-qwen35-maas` | `local-qwen35`, `local-gpt-oss-maas`, `local-gpt-oss`, `local-maas`, `local`, `local-wesh-maas`, `local-wesh` | — | `policies/model-routing/model-routing-policy.yaml` |
| `monthly-invoice-report` (project-required; prompt: `prompts/monthly-invoice-report.md`) | `C2` | `local-qwen35-maas` | `local-qwen35`, `local-gpt-oss-maas`, `local-gpt-oss`, `local-maas`, `local`, `local-wesh-maas`, `local-wesh` | — | `policies/model-routing/model-routing-policy.yaml` |
| `check-my-drive-and-mail` | `C2` | `local-qwen35-maas` | `local-qwen35`, `local-gpt-oss-maas`, `local-gpt-oss`, `local-maas`, `local`, `local-wesh-maas`, `local-wesh` | — | `policies/model-routing/model-routing-policy.yaml` |

**Available models** (ADR-0419, generated): the union of every model reachable by any task or prompt slot above, at any classification - `local-maas`, `local`, `local-gpt-oss-maas`, `local-gpt-oss`, `local-wesh-maas`, `local-wesh`, `local-qwen35-maas`, `local-qwen35`.

<!-- END GENERATED AUTHORIZATION MATRIX -->
