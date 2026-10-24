# ADR-0307: Support self-service agent onboarding

- **Status:** Superseded by [ADR-0582](0582-serve-a-per-agent-entry-and-descriptive-sheet-from-the-admitted-bundle.md), [ADR-0583](0583-require-group-visibility-and-object-level-authorisation-before-per-agent-entries.md) and [ADR-0584](0584-define-agent-lifecycle-states-roles-and-incident-revocation.md) (2026-10-24) - the `agents/` tree, the `AIAgent` CR and `platform/templates/agent/` this decision scaffolded were removed by WP-156 and WP-165; an agent is now defined in `zuno-demo-agents` and its entry, visibility and lifecycle are governed by those ADRs. Previously: Proposed (deferred)
- **Target:** v0.9 (retargeted from v0.7 on 2026-08-30, same day it was first moved from v0.4 — user decision: Naveo will not be pursued as the new-agent onboarding proof before at least v0.9, possibly later)
- **Date:** 2026-08-15
- **Decision owners:** Zuno Demo architecture team

## Decision

Provide controlled templates, validation and workflows for teams to
define new agents (the stub decision, promoted verbatim from
`docs/roadmap/adr-decisions-v0.3.md`).

A new agent is created from a repository template
(`platform/templates/agent/`) that scaffolds the OKF bundle skeleton,
`AIAgent` CR, Keycloak entitlement fragment, policy entries and a
20-scenario evaluation skeleton. A validation workflow (composing the
OKF, knowledge-reference, policy and contract validators) gates the
onboarding PR; a template-created agent reaches `active` through exactly
the same ADR-0326 completion pattern and ADR-0027/0028 gates as the
first five — self-service changes who authors the definition, never the
acceptance bar.

See [Standard clauses](README.md#standard-clauses) for Context,
Alternatives, Consequences, Security/Operational considerations,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0410](0410-expand-the-agent-catalog-beyond-the-initial-five-agents.md)
- [ADR-0326](0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md)
- [ADR-0327](0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md)
- [ADR-0308](0308-expand-agent-lifecycle-management-through-the-aiagent-operator.md)
- [ADR-0106](0106-enforce-okf-bundle-signing-and-validation.md)
