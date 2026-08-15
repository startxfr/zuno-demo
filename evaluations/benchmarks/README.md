# Benchmark artifacts (ADR-0305, WP-40)

Generated output of `evaluations/benchmark.py`, one `<candidate>.json` per
benchmarked model/adapter candidate - never hand-authored or committed
(`.gitignore`d). See that script's own module docstring for the exact
artifact schema and how to produce one.

Empty today: no WP-34 GPU-trained adapter has been registered yet (the
cluster's GPU capacity is fully committed - see MEMORY.md), so nothing
has been benchmarked. `policies/model-routing/model-routing-policy.yaml`'s
`adapters: []` reflects the same gap - `evaluations/benchmark.py
--check-policy` (ADR-0305's "no artifact, no promotion" enforcement,
wired into `.github/workflows/lint.yml`'s `quality-gate` job) passes
trivially with nothing declared to check.
