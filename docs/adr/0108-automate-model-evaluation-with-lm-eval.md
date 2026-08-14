# ADR-0108: Automate model evaluation with LM-Eval

- **Status:** Partially implemented (gate runner, CI wiring and LMEvalJob manifests merged; GPU cluster runs pending, roadmap WP-10)
- **Target:** v0.1
- **Date:** 2026-08-14
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.1-roadmap entry
(`0100-v0.1-roadmap.md`) to a full record.

Use OpenShift AI's LM-Eval capability (`LMEvalJob` resources on the
DataScienceCluster's evaluation component) to benchmark candidate local
models on declared task suites before they become routable (ADR-0021
classes). Job manifests and task selections are GitOps-managed; results
land in the model quality gate (ADR-0107) as one of its inputs. LM-Eval
complements — never replaces — the per-agent ADR-0027 acceptance suites.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Security/Operational considerations,
Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0019](0019-use-openshift-ai-model-serving-for-local-inference.md)
- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)
- [ADR-0107](0107-introduce-automated-model-quality-gates.md)
