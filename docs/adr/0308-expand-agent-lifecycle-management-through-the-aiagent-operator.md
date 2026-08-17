# ADR-0308: Expand agent lifecycle management through the AIAgent Operator

- **Status:** Implemented - see `operator/aiagent-operator/`. Cluster reconciliation confirmed 2026-08-17: `aiagent-operator` deployed and Ready in `zuno-ai-run`; both live `AIAgent` CRs (Arkos and Naveo) show all five status conditions `True` (`ConfigValid`/`OKFReady`/`FrontendReady`/`BFFReady`/`RuntimeBindingReady`), confirming reconciliation, boundary enforcement and the migration proof all work against a real cluster, not just envtest. (The broader `make d1 check agents` ADR-0053 fleet gate still fails on pre-existing, unrelated scenario/security-check gaps across other agents - not an operator or CR-reconciliation defect; see MEMORY.md's 2026-08-16 note.)
- **Target:** v0.3
- **Date:** 2026-08-15
- **Decision owners:** Zuno Demo architecture team

## Decision

Automate more lifecycle, policy and deployment reconciliation around agent
definitions (the stub decision, promoted verbatim from
`docs/adr/0300-v0.3-roadmap.md`).

Implement the AIAgent Operator against the ADR-0327 contract exactly: the
operator reconciles per-agent frontend/BFF/OKF-reference/NetworkPolicy/
ServiceAccount/RBAC resources and status conditions from
`zuno.ai/v1alpha1 AIAgent` CRs that Git/Argo CD owns; it never installs
shared platform services, never becomes the source of truth for OKF
semantics, never bypasses Argo CD for the CR itself, never broadens
cluster RBAC dynamically, and never creates unrestricted credentials.
Migration is incremental per agent with the plain-manifest path remaining
valid until each agent's CR is adopted.

See [Standard clauses](README.md#standard-clauses) for Context,
Alternatives, Consequences, Security/Operational considerations,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0350](0350-provide-an-aiagent-kubernetes-crd-and-operator.md)
- [ADR-0327](0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md)
- [ADR-0022](0022-use-gitops-managed-declarative-agent-tasks-and-policies.md)
- [ADR-0008](0008-use-one-frontend-and-one-bff-deployment-per-agent.md)
