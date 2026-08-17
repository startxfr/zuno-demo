# ADR-0350: Provide an AIAgent Kubernetes CRD and operator

- **Status:** Implemented - see ADR-0327/ADR-0308 and `operator/aiagent-operator/`.
- **Target:** v0.3
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team
- **Renumbered:** formerly ADR-0026 (2026-08-13 roadmap reorganization), then ADR-0113 (2026-08-15 move to the v0.3 stream)
- **Retargeted:** moved from v0 to v0.1 on 2026-08-04, then from v0.1 to v0.3 on 2026-08-15 - the decision is delivered by the v0.3 stream (ADR-0327 contract, ADR-0308 operator), so it now lives there. The v0 demo deploys each agent as a plain Kubernetes `Deployment` applied by ArgoCD (see ADR-0022); the AIAgent CRD/operator remains the intended v0.1 evolution once the platform hosts more than the single Tekos vertical slice and reconciliation logic earns its cost.

## Decision

Represent agent instances declaratively and reconcile required OpenShift resources through an operator. Not built for v0: with a single functional agent, a plain Deployment plus GitOps-managed manifests achieves the same declarative-and-reviewable property without the cost of a custom controller.

## Evolution (2026-08-15)

This decision is now implemented, in two steps rather than one: ADR-0327 defined the narrow `AIAgent` reconciliation contract first, and ADR-0308 (WP-38) implements the operator against that contract - controller, boundary enforcement, envtest suite and the Arkos migration proof are merged (`operator/aiagent-operator/`; `gitops/charts/arkos/` is now CR-managed). This record's own Status line stayed `Proposed` while ADR-0308 was the ADR carrying the authoritative implementation status, per the immutability boundary (this Decision text is not rewritten to claim implementation itself).

### Evolution (2026-08-17)

ADR-0308 reached `Implemented` (cluster reconciliation confirmed live: `aiagent-operator` deployed and Ready, both the Arkos and Naveo `AIAgent` CRs show all five status conditions `True`), so per the trigger this record itself named above, this ADR's Status line now moves to `Implemented` too.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution and Related ADRs.
