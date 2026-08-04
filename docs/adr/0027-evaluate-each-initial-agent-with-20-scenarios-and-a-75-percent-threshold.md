# ADR-0027: Evaluate each initial agent with 20 scenarios and a 75 percent threshold

- **Status:** Accepted
- **Target:** v0
- **Date:** 2026-08-04

## Context

Agent behavior needs measurable acceptance criteria rather than subjective demo validation only.

## Decision

Maintain 20 scenarios per agent and require an initial 75% pass target. Include human review for Arkos DAT outputs and RAG grounding/citation checks for Tekos.

## Alternatives considered

One generic smoke test; manual ad hoc validation only.

## Consequences

Creates a repeatable baseline across approximately 100 scenarios.

## Security considerations

Evaluation datasets must not contain unsafe real data.

## Operational considerations

v0 may report results; v1 blocks releases on quality gates.

## Migration / evolution

Thresholds can increase as datasets mature.
