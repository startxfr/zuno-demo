# ADR-0305: Introduce automated model benchmarking

- **Status:** Implemented (2026-08-29) - see `evaluations/benchmark.py`. One real candidate benchmarked: `comage-lora` v6 (WP-087/ADR-0526, run `wesh-20260829-145123`), artifact written to `evaluations/benchmarks/comage-lora-wesh-20260829-145123.json` (`overall: PASS`, reusing that run's already-real, already-live-verified gate results rather than re-executing the live acceptance gate a second time).
- **Target:** v0.3
- **Date:** 2026-08-15
- **Decision owners:** Zuno Demo architecture team

## Decision

Benchmark candidate models before routing-policy promotion (the stub
decision, promoted verbatim from `docs/roadmap/adr-decisions-v0.3.md`).

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
