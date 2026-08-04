# ADR-0301: Introduce LoRA and PEFT customization through MLOps pipelines

- **Status:** Proposed
- **Target:** v3
- **Date:** 2026-08-04

## Context

The architecture should be ready for model customization, especially Comage, after RAG/prompting has been measured.

## Decision

Create dataset → train/adapt → evaluate → registry → deployment pipelines for LoRA/PEFT, with dynamic adapter loading when validated.

## Alternatives considered

Full model fine-tuning first; no customization.

## Consequences

Can reduce token usage/latency and improve task relevance if evidence supports it.

## Security considerations

Training data governance and leakage controls are mandatory.

## Operational considerations

Requires GPU scheduling, registry, evaluation, and lifecycle automation.

## Migration / evolution

Only adopt when metrics show value over prompt/RAG baselines.
