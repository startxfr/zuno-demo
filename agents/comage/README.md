# Comage Agent

- **Purpose:** Sales assistant
- **Primary integrations:** Sales data (Salesforce + legacy SXA), Gmail, Drive
- **Initial tasks:** Deal status; opportunity updates; historical deal comparison

## Stage (ADR-0502)

**`zuno.status: active` (2026-08-22)** — promoted at the operator's
explicit direction, ahead of `platform/templates/agent/PROMOTION.md`
steps 1 and 3 formally closing out (see below); the legacy full-skeleton
shape still applies otherwise (the empty `policies/`/`rag/`/`tools/`
directories are retained, not deleted, and still await real content —
`deployment/` and `tests/` no longer are, see below).

- `zuno.status: active` — the portal renders Comage's tile as enabled
  and Agent Runtime's generic dispatch serves `/v1/agents/comage/chat`.
- Deployed by `gitops/charts/comage/` as **raw manifests** (still not
  CR-managed at flip time; only Arkos was migrated as the WP-38 proof
  and Naveo was born CR-managed — Comage's CR migration remains a
  future promotion-time step, out of scope for this flip).
- Real bundle (ADR-0326 slice 2/4, WP-33 repo work merged):
  `retrieve_reason_respond` shape, primary task `check-deal-status`
  plus `update-opportunity-status`, `compare-historical-deals` and
  `check-my-drive-and-mail` — four declared tasks.
- Evaluations: `evaluations/comage/` authored. **A formal human
  scenario-review sign-off and a live 75 % gate run
  (`run_acceptance_gate.py`) are still outstanding as separate,
  documented checkpoints** — PROMOTION.md steps 1 and 3 — even though
  the agent is already live (this flip jumped ahead of them, at the
  operator's own call).
- **Known live-read gap:** `check-deal-status`'s live
  `salesforce.opportunity.read` call cannot succeed yet — `salesforce-mcp`
  has no deployment in-cluster, and its Vault-sourced credentials
  (`salesforce/technical`) are still unresolved (standing operator gap,
  tracked separately). Chat still works: agent-runtime degrades
  gracefully to indexed-only (`knowledge.sales`) context when the live
  tool call fails, it just never reaches `source_mode: live`/`both`
  until that gap closes.

**Next step:** run `platform/templates/agent/PROMOTION.md` steps 1 and 3
retroactively (human scenario review of `evaluations/comage/scenarios.yaml`,
then the live gate) to close out the paperwork the status flip jumped
ahead of; deploy `salesforce-mcp` and fix its Vault secret to close the
live-read gap; CR migration remains a later promotion-time step.

## Declarative structure (ADR-0038: OKF v0.2 Markdown bundles)

```text
comage/
├── README.md
├── agent.okf.md         Agent index bundle (YAML frontmatter + Markdown body)
├── tasks/
│   ├── check-deal-status.md           (primary task)
│   ├── update-opportunity-status.md
│   ├── compare-historical-deals.md
│   └── check-my-drive-and-mail.md
├── prompts/
│   └── check-deal-status.md
├── policies/            (stub)
├── rag/                 (stub)
├── tools/               (stub)
├── deployment/          Generated ADR-0503 snapshot + README (WP-45)
└── tests/               ADR-0504 structure (WP-46; suites fill at promotion)
```

The runtime implementation is shared. This directory contains only
agent-specific declarative behavior, policy, knowledge references and
deployment configuration.
