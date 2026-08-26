# Advantage Agent

- **Purpose:** Sales administration assistant
- **Primary integrations:** Sales data (Salesforce, indexed ADV knowledge)
- **Initial tasks:** New client-PO-received business; monthly in-progress sales reporting

## Stage (ADR-0502)

**Stage 1 with reserved Stage-2 structure** (legacy full-skeleton shape:
empty directories retained, filled at promotion).

- `zuno.status: placeholder` — "coming soon" tile; no live chat route.
- Deployed by `gitops/charts/advantage/` as **raw manifests** (not yet
  CR-managed; CR migration is a promotion-time step).
- Real bundle (ADR-0326 slice 3/4, WP-35 repo work merged):
  `retrieve_reason_respond` shape, primary task
  `answer-project-question` plus `identify-new-business-with-po`,
  `monthly-sales-report` and `check-my-drive-and-mail` — four declared
  tasks.
- Evaluations: `evaluations/advantage/` authored (including its
  hand-authored narrative security checks); **human scenario review,
  the 75 % gate are the open promotion steps** (per WP-35). Aramis
  live verification is no longer one of them: ADR-0218 dropped the
  adapter, leaving `knowledge.adv` with no source and its sourcing an
  open decision for this slice.

**Next step:** `platform/templates/agent/PROMOTION.md` from step 1
(scenario review); CR migration alongside step 2.

## Declarative structure (ADR-0038: OKF v0.2 Markdown bundles)

```text
advantage/
├── README.md
├── agent.okf.md         Agent index bundle (YAML frontmatter + Markdown body)
├── tasks/
│   ├── answer-project-question.md     (primary task)
│   ├── identify-new-business-with-po.md
│   ├── monthly-sales-report.md
│   └── check-my-drive-and-mail.md
├── prompts/
│   └── answer-project-question.md
├── policies/            (stub)
├── rag/                 (stub)
├── tools/               (stub)
├── deployment/          Generated ADR-0503 snapshot + README (WP-45)
└── tests/               ADR-0504 structure (WP-46; suites fill at promotion)
```

The runtime implementation is shared. This directory contains only
agent-specific declarative behavior, policy, knowledge references and
deployment configuration.
