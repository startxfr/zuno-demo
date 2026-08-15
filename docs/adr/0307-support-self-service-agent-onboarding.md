# ADR-0307: Support self-service agent onboarding

- **Status:** Partially implemented (template, validation workflow and sixth-agent definition merged; deployment gate pending)
- **Target:** v0.3
- **Date:** 2026-08-15
- **Decision owners:** Zuno Demo architecture team

## Decision

Provide controlled templates, validation and workflows for teams to
define new agents (the stub decision, promoted verbatim from
`docs/adr/0300-v0.3-roadmap.md`).

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
