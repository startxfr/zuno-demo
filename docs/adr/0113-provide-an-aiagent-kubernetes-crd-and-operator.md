# ADR-0113: Provide an AIAgent Kubernetes CRD and operator

- **Status:** Proposed
- **Target:** v0.1
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team
- **Renumbered:** formerly ADR-0026 (2026-08-13 roadmap reorganization)
- **Retargeted:** moved from v0 to v0.1 on 2026-08-04. The v0 demo deploys each agent as a plain Kubernetes `Deployment` applied by ArgoCD (see ADR-0022); the AIAgent CRD/operator remains the intended v0.1 evolution once the platform hosts more than the single Tekos vertical slice and reconciliation logic earns its cost.

## Decision

Represent agent instances declaratively and reconcile required OpenShift resources through an operator. Not built for v0: with a single functional agent, a plain Deployment plus GitOps-managed manifests achieves the same declarative-and-reviewable property without the cost of a custom controller.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution and Related ADRs.
