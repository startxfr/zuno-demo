# Naveo Agent

- **Purpose:** Onboarding assistant for new team members (synthetic
  persona, ADR-0410's sixth-agent template proof)
- **Primary integrations:** Technical RAG, project memory, Confluence,
  Drive, web search — existing capabilities only, by construction
- **Initial tasks:** Onboarding Q&A

## Stage (ADR-0502)

**Stage 1 — scaffolded (the canonical Stage-1 shape).** Naveo is the
generator's own output (`platform/templates/agent/scaffold_agent.py`,
ADR-0307/WP-41), unmodified except for reviewed fixes, and defines what
Stage 1 means: this lean bundle plus a CR-managed chart — no README-era
skeleton directories at all until promotion grows them.

- `zuno.status: placeholder` — "coming soon" tile; generic dispatch
  404s until the flip.
- **CR-managed from day one**: `gitops/charts/naveo/` renders a single
  `AIAgent` CR (the first agent never to have a raw-manifest chart);
  both live CRs (Arkos, Naveo) confirmed all-conditions-`True`
  in-cluster 2026-08-17.
- Keycloak identity, Vault seeds, check.yml wiring and policy
  verification (zero edits needed) all done — see `NEXT_STEPS.md`
  steps 1–6.
- Evaluations: `evaluations/naveo/` scaffolded; **human scenario review
  and the operator deploy + 75 % gate are the open promotion steps**
  (NEXT_STEPS 7–8, now the PROMOTION.md checklist).

**Next step:** `platform/templates/agent/PROMOTION.md` step 1 (scenario
review of `evaluations/naveo/scenarios.yaml`).

## Declarative structure (ADR-0038; Stage-1 lean shape)

```text
naveo/
├── README.md
├── agent.okf.md            Agent index bundle (YAML frontmatter + Markdown body)
├── keycloak-fragment.json  Identity reference copy (merged into realm-zuno.json)
├── NEXT_STEPS.md           Onboarding checklist (steps 1-6 done; 7 = promotion)
├── tasks/
│   └── answer-onboarding-question.md   (primary task)
└── prompts/
    └── answer-onboarding-question.md
```

`deployment/`, `policies/`, `rag/`, `tools/` and `tests/` do not exist
yet by design (ADR-0502 Stage 1) — they are born at promotion with real
ADR-0503/ADR-0504 content, never as empty stubs.

The runtime implementation is shared. This directory contains only
agent-specific declarative behavior, policy and knowledge references.
