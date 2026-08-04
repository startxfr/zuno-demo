# ADR-0002: Target OpenShift 4.20 with OpenShift AI 3.5 EA2 for the MVP

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

The demo requires OpenShift AI 3.5 capabilities and accepts Early Access or Technology Preview features for an internal MVP.

## Decision

Use OpenShift 4.20 AWS IPI with OpenShift AI 3.5 EA2 as the v0 baseline.

## Alternatives considered

ROSA; later OpenShift versions before confirmed compatibility; a Kubernetes-only deployment.

## Consequences

The MVP can use the required OpenShift AI features but must clearly distinguish MVP support posture from later production supportability.

## Security considerations

EA/TP limitations must be documented and production data exposure minimized.

## Operational considerations

Version compatibility must be checked by precheck automation.

## Migration / evolution

Move to a fully supported OpenShift AI/OpenShift combination during industrialization.
