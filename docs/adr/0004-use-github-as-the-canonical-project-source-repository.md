# ADR-0004: Use GitHub as the canonical project source repository

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

The project now has a public `startxfr/zuno-demo` repository and all future deliverables must be maintained there.

## Decision

Treat GitHub as the source of truth for code, documentation, ADRs, agent definitions, and GitOps content.

## Alternatives considered

GitLab as source of truth; dual-master repositories.

## Consequences

Removes ambiguity and centralizes review/history.

## Security considerations

Repository is public, so data and secret hygiene is mandatory.

## Operational considerations

External mirrors are secondary and must not become competing sources of truth.

## Migration / evolution

A future CI mirror can be introduced without changing canonical source ownership.
