# Comage Agent

- **Purpose:** Sales assistant
- **Primary integrations:** Sales data (Salesforce + legacy SXA), Gmail, Drive
- **Initial tasks:** Deal status; opportunity updates; historical deal comparison

## Stage (ADR-0502)

**Stage 1 with reserved Stage-2 structure** (legacy full-skeleton shape:
empty directories retained, filled at promotion).

- `zuno.status: placeholder` — "coming soon" tile; no live chat route.
- Deployed by `gitops/charts/comage/` as **raw manifests** (not yet
  CR-managed; only Arkos was migrated as the WP-38 proof and Naveo was
  born CR-managed — Comage's CR migration is a promotion-time step).
- Real bundle (ADR-0326 slice 2/4, WP-33 repo work merged):
  `retrieve_reason_respond` shape, primary task `check-deal-status`
  plus `update-opportunity-status`, `compare-historical-deals` and
  `check-my-drive-and-mail` — four declared tasks.
- Evaluations: `evaluations/comage/` authored; **human scenario review,
  the 75 % gate and live Salesforce verification are the open promotion
  steps** (per WP-33; sandbox Salesforce credentials are a standing
  operator gap).

**Next step:** `platform/templates/agent/PROMOTION.md` from step 1
(scenario review); CR migration alongside step 2.

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
