# Soursage Agent

- **Purpose:** Recruiting assistant — source new consultant candidates
  and match existing consultants to missions (ADR-0349 §6)
- **Primary integrations (intended):** Workday
  (`workday.profile.any.read`, the read-only ADR-0340 scoped capability
  WP-32 registered) and a future LinkedIn capability
- **Initial tasks:** none yet — `coming-soon` placeholder with
  `allowed_tools: []`

## Stage (ADR-0502)

**Stage 1 — scaffolded (identity-first variant, brought to parity by
WP-43).** Soursage predates the generator (ADR-0349 created only the
identity footprint); WP-43 added the Stage-1 identity artifacts
(`keycloak-fragment.json`, `NEXT_STEPS.md`) from the real generator's
output while keeping the hand-authored bundle. Deliberately withheld
until someone chooses to build Soursage: gitops chart/Applications and
the evaluations skeleton (see `NEXT_STEPS.md` steps 4 and 7).

- `zuno.status: placeholder` — access-gated "coming soon" tile only.
- Identity live since ADR-0349: `soursage-frontend` Keycloak client +
  `agent_soursage` entitlement group.
- **Zero capability by construction**: `tasks/coming-soon.md` declares
  `allowed_tools: []` and no knowledge domains; `recrut` and `sales`
  are the intended business roles; `preferred_classification: C2`
  (candidate/consultant profile data needs context filtering).
- No chart, no CR, no evaluations, no live route.

**Next step:** author real tasks through the ADR-0307 template workflow
(which also brings chart + evaluations), then
`platform/templates/agent/PROMOTION.md`.

## Declarative structure (ADR-0038; Stage-1 identity-first shape)

```text
soursage/
├── README.md
├── agent.okf.md            Agent index bundle (YAML frontmatter + Markdown body)
├── keycloak-fragment.json  Identity reference copy (identity live per ADR-0349)
├── NEXT_STEPS.md           Onboarding checklist (annotated for the partial state)
└── tasks/
    └── coming-soon.md      Placeholder task, allowed_tools: []
```

The runtime implementation is shared. This directory contains only
agent-specific declarative behavior, policy and knowledge references.
