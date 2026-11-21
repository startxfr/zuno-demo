# WP-328: Qualify a portfolio of European models served locally

- **State:** Not started (proposed by ADR-0625 on 2026-11-21; the ADR is `Proposed`, so this work package is not approved)
- **ADRs:** [ADR-0625](../../adr/0625-evolve-zuno-toward-a-modular-sovereign-enterprise-ai-platform.md)
- **Depends on:** none
- **Related:** [ADR-0020](../../adr/0020-support-both-local-and-external-llm-providers.md), [ADR-0417](../../adr/0417-consume-codestral-via-mistral-api.md), [ADR-0541](../../adr/0541-integrate-mistral-and-gpt-oss-120b-as-maas-externalmodels.md), [ADR-0537](../../adr/0537-integrate-rhoai-hardware-profiles-and-maas-external-models.md)
- **Target:** v0.19
- **Estimated files touched:** ~8: model entries, evaluation runs, a matrix page, this brief

## Goal

A qualification matrix of European-origin models with locally deployable weights, measured on the serving stack actually used.

Horizon in the ADR's indicative roadmap: across the horizons. The horizons count from the start of an approved initiative. They are not calendar dates.

## Proposed work

1. Choose the candidates (Mistral AI families first) and the hardware configurations.
2. Evaluate each one: licence, weight availability, provenance, runtime compatibility, GPU footprint, performance, quality, tool calling and structured output (finding F6).
3. Add regression tests for tool calling and RAG after fine-tuning.

## Existing work it builds on

- Mistral models are consumed as a service today ([ADR-0417](../../adr/0417-consume-codestral-via-mistral-api.md), [ADR-0541](../../adr/0541-integrate-mistral-and-gpt-oss-120b-as-maas-externalmodels.md)) under the provider rules of [ADR-0020](../../adr/0020-support-both-local-and-external-llm-providers.md). Local serving uses the hardware profiles of [ADR-0537](../../adr/0537-integrate-rhoai-hardware-profiles-and-maas-external-models.md).

## Acceptance

- The matrix records, for each model, the measured values and the licence.
- No model is removed solely because of its origin before its evaluation.
