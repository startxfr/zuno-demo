# ADR-0001: Use a monorepo for the Zuno platform

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

The MVP contains shared platform components, five first agent instances, infrastructure automation, policies, data migrations, and documentation that evolve together.

## Decision

Use one GitHub repository for the demo platform, agents, documentation, automation, and GitOps definitions.

## Alternatives considered

Separate repository per agent; separate repository per platform component.

## Consequences

Cross-cutting changes are atomic and easier to review; repository boundaries do not provide isolation, so ownership must be expressed through review and directory conventions.

## Security considerations

Public repository controls must prevent secrets and real commercial data from entering any directory.

## Operational considerations

CI can validate the whole platform contract from one revision.

## Migration / evolution

Split repositories only if ownership, release cadence, or scale later justifies the operational cost.
