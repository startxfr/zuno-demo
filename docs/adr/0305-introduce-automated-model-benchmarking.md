# ADR-0305: Introduce automated model benchmarking

- **Status:** Partially implemented (benchmark harness, objectives and reporting merged; live loop pending)
- **Target:** v0.3
- **Date:** 2026-08-15
- **Decision owners:** Zuno Demo architecture team

## Decision

Benchmark candidate models before routing-policy promotion (the stub
decision, promoted verbatim from `docs/adr/0300-v0.3-roadmap.md`).

Every candidate model or adapter is benchmarked before routing-policy
promotion: LM-Eval task suites (ADR-0108) plus the target agents'
acceptance gates (ADR-0107), producing a versioned, comparable result
artifact stored alongside the Model Registry entry. A candidate without a
benchmark artifact cannot be referenced by a routing-policy change.

See [Standard clauses](README.md#standard-clauses) for Context,
Alternatives, Consequences, Security/Operational considerations,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0107](0107-introduce-automated-model-quality-gates.md)
- [ADR-0108](0108-automate-model-evaluation-with-lm-eval.md)
- [ADR-0302](0302-build-dataset-to-model-mlops-pipelines.md)
- [ADR-0304](0304-optimize-model-selection-using-quality-cost-and-latency.md)
