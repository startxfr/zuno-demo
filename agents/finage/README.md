# Finage Agent

- **Purpose:** Finance assistant
- **Primary integrations:** Sales and invoice data
- **Initial tasks:** Billable business; monthly invoice reporting

## Stage (ADR-0502)

**Stage 1 with reserved Stage-2 structure** (legacy full-skeleton shape:
empty directories retained, filled at promotion).

- `zuno.status: placeholder` — "coming soon" tile; no live chat route.
- Deployed by `gitops/charts/finage/` as **raw manifests** (not yet
  CR-managed; CR migration is a promotion-time step).
- Real bundle (ADR-0326 slice 4/4 — the slice that closed ADR-0326's
  repo side, WP-36 repo work merged): `retrieve_reason_respond` shape,
  primary task `answer-finance-question` plus
  `identify-business-ready-to-invoice`, `monthly-invoice-report` and
  `check-my-drive-and-mail` — four declared tasks.
- Evaluations: `evaluations/finage/` authored. Human scenario review and
  a live 75% gate run both completed 2026-08-30 (WP-36) — the suite is
  explicitly written for placeholder behavior, Layer 1 100% (20/20).
  D10 (no finance-specific RAG domain, deterministic `sxa.*` capabilities
  instead) is the decided, final scope — there is no pending "flip to
  active" step.
- OKF-stream note: the two invoice tasks are the designated first
  `zuno.project_required` candidates (ADR-0512/WP-55) — Finage is the
  project-binding exemplar.

**Next step:** none for promotion — this agent is deliberately staying
`placeholder` (D10). CR migration remains available whenever an operator
wants to do it, independent of that decision.

## Declarative structure (ADR-0038: OKF v0.2 Markdown bundles)

```text
finage/
├── README.md
├── agent.okf.md         Agent index bundle (YAML frontmatter + Markdown body)
├── tasks/
│   ├── answer-finance-question.md     (primary task)
│   ├── identify-business-ready-to-invoice.md
│   ├── monthly-invoice-report.md
│   └── check-my-drive-and-mail.md
├── prompts/
│   └── answer-finance-question.md
├── policies/            (stub)
├── rag/                 (stub)
├── tools/               (stub)
├── deployment/          Generated ADR-0503 snapshot + README (WP-45)
└── tests/               ADR-0504 structure (WP-46; suites fill at promotion)
```

The runtime implementation is shared. This directory contains only
agent-specific declarative behavior, policy, knowledge references and
deployment configuration.
