# ADR-0350: Provide an AIAgent Kubernetes CRD and operator

- **Status:** Proposed
- **Target:** v0.3
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team
- **Renumbered:** formerly ADR-0026 (2026-08-13 roadmap reorganization), then ADR-0113 (2026-08-15 move to the v0.3 stream)
- **Retargeted:** moved from v0 to v0.1 on 2026-08-04, then from v0.1 to v0.3 on 2026-08-15 - the decision is delivered by the v0.3 stream (ADR-0327 contract, ADR-0308 operator), so it now lives there. The v0 demo deploys each agent as a plain Kubernetes `Deployment` applied by ArgoCD (see ADR-0022); the AIAgent CRD/operator remains the intended v0.1 evolution once the platform hosts more than the single Tekos vertical slice and reconciliation logic earns its cost.

## Decision

Represent agent instances declaratively and reconcile required OpenShift resources through an operator. Not built for v0: with a single functional agent, a plain Deployment plus GitOps-managed manifests achieves the same declarative-and-reviewable property without the cost of a custom controller.

## Evolution (2026-08-15)

This decision is now implemented, in two steps rather than one: ADR-0327 defined the narrow `AIAgent` reconciliation contract first, and ADR-0308 (WP-38) implements the operator against that contract - controller, boundary enforcement, envtest suite and the Arkos migration proof are merged (`operator/aiagent-operator/`; `gitops/charts/arkos/` is now CR-managed). This record's own Status line stays `Proposed` rather than moving to `Implemented` directly: ADR-0308 is the ADR that actually carries the implementation status (`Partially implemented` pending live cluster reconciliation), and per the immutability boundary this Decision text is not rewritten to claim it. See ADR-0308's own Status line for the current, authoritative state; this ADR moves to `Implemented - see ADR-0327/ADR-0308 and operator/aiagent-operator/.` only once ADR-0308 itself reaches `Implemented`.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution and Related ADRs.
