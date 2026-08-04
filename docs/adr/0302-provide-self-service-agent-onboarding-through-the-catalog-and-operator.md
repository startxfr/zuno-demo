# ADR-0302: Provide self-service agent onboarding through the catalog and operator

- **Status:** Proposed
- **Target:** v3
- **Date:** 2026-08-04

## Context

The long-term platform goal is to add agents primarily through declarative definitions.

## Decision

Expose governed self-service onboarding that validates OKF profile, policies, evaluations, and deployment prerequisites before the AIAgent operator reconciles the instance.

## Alternatives considered

Platform-team-only manual onboarding.

## Consequences

Scales the catalog and reduces bespoke engineering.

## Security considerations

Self-service cannot bypass review, signing, RBAC, or policy gates.

## Operational considerations

Requires strong status, documentation, and templates.

## Migration / evolution

Build on v0 operator and v1 quality/security gates.
