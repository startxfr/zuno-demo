# ADR-0022: Manage agent definitions and policies through GitOps review

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

Behavior, prompts, tools, model rules, and permissions can materially change business outcomes.

## Decision

Store agent bundles and policies in GitHub and require pull-request human review before merge/deployment.

## Alternatives considered

Live edits in production UI; runtime database as source of truth.

## Consequences

Changes are auditable and reproducible.

## Security considerations

Review process reduces unauthorized capability expansion.

## Operational considerations

Runtime refresh without deployment is not required in v0.

## Migration / evolution

v1 adds bundle signature enforcement and automated quality gates.
