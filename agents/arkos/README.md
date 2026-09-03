# Arkos Agent

- **Purpose:** Architecture assistant
- **Primary integrations:** Technical RAG, Confluence, Google Drive/Docs,
  Mermaid diagram generation (ADR-0516 - supersedes the originally-planned
  Lucidchart integration, which was never built).
  Photorealistic image generation (stable-diffusion-xl, ADR-0415) is not
  offered to Arkos - it's Comage-exclusive, scoped to marketing visuals.
- **Initial tasks:** Draft architecture testimonial (DAT); prepare Odyssey
  workshop presentations; structure a customer demo; write code

## Stage (ADR-0502)

**`zuno.status: active` (WP-11, 2026-08-21)** — promoted at the
operator's explicit direction, ahead of `platform/templates/agent/
PROMOTION.md` steps 1 and 3 formally closing out (see below); the legacy
full-skeleton shape still applies otherwise (the empty `policies/`/
`rag/`/`tools/` directories are retained, not deleted, and still await
real content - `deployment/` and `tests/` no longer are, see below).

- `zuno.status: active` — the portal renders Arkos's tile as enabled and
  Agent Runtime's generic dispatch serves `/v1/agents/arkos/chat`.
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
  PROMOTION.md steps 1 and 3 (human scenario review, live 75% gate run)
  completed retroactively 2026-08-30 - see WP-31's own "2026-08-30
  retroactive gate catch-up" section for the full result. Closed the gap
  WP-11's earlier status flip left open.

**Known open item:** scenario 9 (`structure-demo` streaming) times out at
30s on every run - a single-call path which, until 2026-09-03, had no
`model-routing-policy.yaml` override at all. It was described here and in
WP-31 as riding the WP-096 `qwen3.5-9b` fleet default; that was wrong. With
no entry it fell through to `provider-routing.yaml` file order and was
answered by `local-maas`/`local` = `qwen3.6-27b-instruct`, as this bundle's
own generated matrix showed all along. It now carries an explicit entry
pinning that same chain (ADR-0531's correction note), so the timeout is
unchanged and still open - but it is a 27B timeout, not a 9B one. Non-blocking (Layer 1
still clears the 75% threshold at 19/20) but unresolved; see WP-31.

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
