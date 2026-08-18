---
okf_version: v0.2
type: agent
title: Finage
description: >-
  Finance assistant. Identifies business ready to invoice and produces
  monthly invoice reporting, drawing on deterministic legacy SXA
  revenue/billing queries and durable project memory - never live
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
  - "sales-db (legacy SXA, deterministic queries only, WP-23)"
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
    notes: >-
      Placeholder pending the live acceptance gate; C2 default, escalating
      to C3 whenever a turn touches the deterministic legacy SXA
      aggregation/lookup capabilities (`financial-data`/`hr-data` tier,
      policies/data-classification/classification.yaml, ADR-0034).
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
than inventing one, Finage's tasks declare only `knowledge.project`
(cross-agent project memory) for retrieval, plus the deterministic
`sxa.*` capabilities (`sxa.customer.read`, `sxa.quote.read`,
`sxa.aggregate.revenue-by-year`, `sxa.record.lookup`) already exposed by
`components/mcp-servers/sales-db` (WP-23) for exact billing/revenue
numbers - `policies/knowledge/knowledge-policy.yaml`'s own
`knowledge.sxa-legacy` entry deliberately excludes `finance` from its
`allowed_groups` (ADR-0340's access-intent table, WP-32), so this gap is
a real, pre-existing policy boundary honored here, not overridden.

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
`policies/tools/tool-policy.yaml`'s `sxa.*`/Drive/Gmail entries).

<!-- BEGIN GENERATED AUTHORIZATION MATRIX (ADR-0503) - do not edit; regenerate with: python3 platform/okf/generate_authorization_matrix.py -->

## Authorization matrix

Generated per ADR-0503 from this bundle's frontmatter, `policies/tools/tool-policy.yaml` and `policies/knowledge/knowledge-policy.yaml` — the enforced intersection (ADR-0011/ADR-0203) restated for review, never read at runtime. Entitlement (ADR-0040): `agent_finage`; model classification ceiling (ADR-0021): `C2`; status: `placeholder`.

| Task (FOR WHAT) | Resource (WHAT) | Kind | Capability / server | Min class | Business roles (WHO) | Ext-model context | Quota | Policy source |
|---|---|---|---|---|---|---|---|---|
| `answer-finance-question` (primary; prompt: `prompts/answer-finance-question.md`) | `web_search` | tool | `web.page.search` @ web-search | C1 | sales, consultant, adv, finance, board | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `web_search` |
| `answer-finance-question` (primary; prompt: `prompts/answer-finance-question.md`) | `knowledge.project` | knowledge | — | — | consultant, board, sales, adv, finance, cdp | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.project` |
| `identify-business-ready-to-invoice` | `sxa.customer.read` | tool | `sxa.customer.read` @ sales-db | C2 | sales, adv, board, finance | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `get_customer` |
| `identify-business-ready-to-invoice` | `sxa.quote.read` | tool | `sxa.quote.read` @ sales-db | C2 | sales, adv, board, finance | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `get_quote` |
| `monthly-invoice-report` | `sxa.aggregate.revenue-by-year` | tool | `sxa.aggregate.revenue-by-year` @ sales-db | C3 | sales, board, finance | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `aggregate_revenue_by_year` |
| `monthly-invoice-report` | `sxa.record.lookup` | tool | `sxa.record.lookup` @ sales-db | C3 | sales, board, finance | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `lookup_record` |
| `check-my-drive-and-mail` | `list_drive_files` | tool | `drive.document.search` @ google-workspace | C1 | consultant, board, cdp, sales, adv, finance | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `list_drive_files` |
| `check-my-drive-and-mail` | `read_gmail` | tool | `gmail.message.read` @ google-workspace | C1 | consultant, board, cdp, sales, adv, finance | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `read_gmail` |

<!-- END GENERATED AUTHORIZATION MATRIX -->
