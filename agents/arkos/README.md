# Arkos Agent

- **Purpose:** Architecture assistant
- **Primary integrations:** Technical RAG, Confluence, Google Drive/Docs, Lucidchart
- **Initial tasks:** Draft architecture testimonial (DAT); prepare Odyssey
  workshop presentations; structure a customer demo; write code

## Stage (ADR-0502)

**Stage 1, promotion steps 1-4 of `platform/templates/agent/
PROMOTION.md` complete** (the legacy full-skeleton shape: the empty
`policies/`/`rag/`/`tools/` directories are retained, not deleted, and
still await real content - `deployment/` and `tests/` no longer are, see
below).

- `zuno.status: placeholder` — the portal renders "coming soon" and
  Agent Runtime's generic dispatch 404s `/v1/agents/arkos/chat` until
  the flip.
- **CR-managed live**: `gitops/charts/arkos/` renders a single
  `AIAgent` CR (the WP-38 migration proof; all five status conditions
  confirmed `True` in-cluster 2026-08-17). Arkos is the walking example
  of ADR-0502 clause 2: directory shape says less than criteria do.
- Real bundle (ADR-0326 slice 1/4, WP-31 repo work merged; WP-6/WP-7
  extended it 2026-08-20): `plan_draft_write` graph shape (ADR-0342's
  second shape), four tasks - `draft-architecture-testimonial` (primary),
  `workshop-presentation` (ADR-0514: a second kind through the same
  plan/retrieve/draft/reflect/write path), `structure-demo` and
  `write-code` (both early-exit branches, never touching
  retrieve/draft/write).
- `deployment/` (ADR-0503) and `tests/{contract,tasks,prompts}`
  (ADR-0504) carry real, green content (WP-9) - PROMOTION.md step 4 is
  done, ahead of Tekos itself, which still carries only the `tests/`
  README stubs.
- Evaluations: `evaluations/arkos/scenarios.yaml` authored and updated
  for the two new tasks (WP-10 - scenarios 8/9 now exercise
  workshop-presentation/structure-demo instead of generic DAT text).
  **Human scenario review and the live 75 % gate run remain the open
  promotion steps** (plus Google + Confluence live verification, per
  WP-31) - PROMOTION.md steps 1 and 3.

**Next step:** `platform/templates/agent/PROMOTION.md` step 1 (your
human scenario review of `evaluations/arkos/scenarios.yaml`, especially
the updated scenarios 8/9), then step 3 (live `run_acceptance_gate.py`)
and step 5 (flip `zuno.status: active`) — Arkos is otherwise ready for
Stage 2.

## Declarative structure (ADR-0038: OKF v0.2 Markdown bundles)

```text
arkos/
├── README.md
├── agent.okf.md         Agent index bundle (YAML frontmatter + Markdown body)
├── tasks/
│   ├── draft-architecture-testimonial.md   (primary task)
│   ├── workshop-presentation.md
│   ├── structure-demo.md
│   └── write-code.md
├── prompts/
│   ├── draft-architecture-testimonial.md
│   ├── draft-architecture-testimonial--reflect.md
│   ├── workshop-presentation.md
│   ├── workshop-presentation--reflect.md
│   └── structure-demo.md
├── policies/            (stub)
├── rag/                 (stub)
├── tools/               (stub)
├── deployment/          Generated ADR-0503 snapshot + README (WP-45)
└── tests/               ADR-0504 suites, real content (WP-9)
```

The runtime implementation is shared. This directory contains only
agent-specific declarative behavior, policy, knowledge references and
deployment configuration.
