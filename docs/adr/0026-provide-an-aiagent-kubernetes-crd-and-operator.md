# ADR-0026: Provide an AIAgent Kubernetes CRD and operator

- **Status:** Proposed
- **Target:** v1
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team
- **Retargeted:** moved from v0 to v1 on 2026-08-04. The v0 demo deploys each agent as a plain Kubernetes `Deployment` applied by ArgoCD (see ADR-0022); the AIAgent CRD/operator remains the intended v1 evolution once the platform hosts more than the single Tekos vertical slice and reconciliation logic earns its cost.

## Context

Zuno Demo requires an explicit, reviewable architecture decision so implementation, security and roadmap work remain aligned across the MVP and future releases.

## Decision

Represent agent instances declaratively and reconcile required OpenShift resources through an operator. Not built for v0: with a single functional agent, a plain Deployment plus GitOps-managed manifests achieves the same declarative-and-reviewable property without the cost of a custom controller.

## Alternatives considered

Alternatives remain valid when documented in implementation discussions, but this ADR records the selected direction for the stated target release.

## Consequences

Implementation and documentation must follow this decision. Any material change requires a superseding ADR and an explicit migration/evolution note.

## Security considerations

Security implications must be evaluated during implementation. This decision must not weaken identity propagation, data classification, least privilege, secret management or auditability.

## Operational considerations

Operational checks, observability and rollback/diagnostic procedures must be added as the corresponding capability becomes executable.

## Migration / evolution

Future changes must be documented by a new ADR using `Supersedes ADR-0026` when applicable.

## Related ADRs

See [ADR index](README.md).
