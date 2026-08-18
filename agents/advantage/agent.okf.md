---
okf_version: v0.2
type: agent
title: Advantage
description: >-
  Sales administration assistant. Surfaces new business whose client
  purchase order has just been received and produces monthly in-progress
  sales reporting, drawing on ADV/project knowledge asynchronously
  ingested from Aramis - never live Salesforce data (ADR-0326: explicit
  cross-domain boundary, not implicit inheritance from Comage).
provenance:
  maintainer: Zuno Demo architecture team
  repository: zuno-demo
verification:
  status: unverified
freshness:
  last_reviewed: "2026-08-05"
sources:
  - "knowledge.adv (asynchronously ingested from Aramis, WP-22)"
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
      domain covers Aramis-sourced ADV content too, ADR-0034).
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
declares no `live_read_tool` at all (no live Aramis MCP capability exists
yet - WP-22 built a batch ingestion adapter, not a real-time query tool).
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

Generated per ADR-0503 from this bundle's frontmatter, `policies/tools/tool-policy.yaml` and `policies/knowledge/knowledge-policy.yaml` — the enforced intersection (ADR-0011/ADR-0203) restated for review, never read at runtime. Entitlement (ADR-0040): `agent_advantage`; model classification ceiling (ADR-0021): `C2`; status: `placeholder`.

| Task (FOR WHAT) | Resource (WHAT) | Kind | Capability / server | Min class | Business roles (WHO) | Ext-model context | Quota | Policy source |
|---|---|---|---|---|---|---|---|---|
| `answer-project-question` (primary; prompt: `prompts/answer-project-question.md`) | `web_search` | tool | `web.page.search` @ web-search | C1 | sales, consultant, adv, finance, board | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `web_search` |
| `answer-project-question` (primary; prompt: `prompts/answer-project-question.md`) | `knowledge.adv` | knowledge | — | C2 | adv, board, cdp, finance | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.adv` |
| `answer-project-question` (primary; prompt: `prompts/answer-project-question.md`) | `knowledge.project` | knowledge | — | — | consultant, board, sales, adv, finance, cdp | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.project` |
| `identify-new-business-with-po` | `knowledge.adv` | knowledge | — | C2 | adv, board, cdp, finance | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.adv` |
| `monthly-sales-report` | `knowledge.adv` | knowledge | — | C2 | adv, board, cdp, finance | — | `standard` (user 60 req/5m) | `knowledge/knowledge-policy.yaml` `knowledge.adv` |
| `check-my-drive-and-mail` | `list_drive_files` | tool | `drive.document.search` @ google-workspace | C1 | consultant, board, cdp, sales, adv, finance | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `list_drive_files` |
| `check-my-drive-and-mail` | `read_gmail` | tool | `gmail.message.read` @ google-workspace | C1 | consultant, board, cdp, sales, adv, finance | allowed | `standard` (user 60 req/5m) | `tools/tool-policy.yaml` `read_gmail` |

<!-- END GENERATED AUTHORIZATION MATRIX -->
