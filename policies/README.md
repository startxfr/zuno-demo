# Policies

The platform's own policies: data classification, autonomous optimization
and database actions. They describe what the platform offers and stay here
(ADR-0576 clause 2).

The corp policies that bound agents - tools, knowledge, quotas, model
routing, guardrails, limits and the model catalog - live in
[startxfr/zuno-demo-agents](https://github.com/startxfr/zuno-demo-agents)
(ADR-0576) and reach this platform inside the release pinned in
`platform/okf/agents.lock` (ADR-0580), under the same `policies/<name>/`
paths. Readers here take them from the admitted release
(`platform/okf/release_cache.py`), never from a copy in this repository.
