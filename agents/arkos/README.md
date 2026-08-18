# Arkos Agent

- **Purpose:** Architecture assistant
- **Primary integrations:** Technical RAG, Confluence, Google Drive/Docs, Lucidchart
- **Initial tasks:** Draft architecture testimonial (DAT); prepare Odyssey workshops

## Stage (ADR-0502)

**Stage 1 with reserved Stage-2 structure** (the legacy full-skeleton
shape: the empty directories are retained, not deleted, and gain real
content at promotion).

- `zuno.status: placeholder` — the portal renders "coming soon" and
  Agent Runtime's generic dispatch 404s `/v1/agents/arkos/chat` until
  the flip.
- **CR-managed live**: `gitops/charts/arkos/` renders a single
  `AIAgent` CR (the WP-38 migration proof; all five status conditions
  confirmed `True` in-cluster 2026-08-17). Arkos is the walking example
  of ADR-0502 clause 2: directory shape says less than criteria do.
- Real bundle (ADR-0326 slice 1/4, WP-31 repo work merged):
  `plan_draft_write` graph shape (ADR-0342's second shape),
  one task (`draft-architecture-testimonial`).
- Evaluations: `evaluations/arkos/` authored; **human scenario review
  and the 75 % gate are the open promotion steps** (plus Google +
  Confluence live verification, per WP-31).

**Next step:** `platform/templates/agent/PROMOTION.md` from step 1
(scenario review) — Arkos is the closest agent to Stage 2.

## Declarative structure (ADR-0038: OKF v0.2 Markdown bundles)

```text
arkos/
├── README.md
├── agent.okf.md         Agent index bundle (YAML frontmatter + Markdown body)
├── tasks/
│   └── draft-architecture-testimonial.md   (primary task)
├── prompts/
│   └── draft-architecture-testimonial.md
├── policies/            (stub)
├── rag/                 (stub)
├── tools/               (stub)
├── deployment/          Generated ADR-0503 snapshot + README (WP-45)
└── tests/               (stub until WP-46's ADR-0504 structure)
```

The runtime implementation is shared. This directory contains only
agent-specific declarative behavior, policy, knowledge references and
deployment configuration.
