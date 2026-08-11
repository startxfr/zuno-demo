# ADR-0327: Define the AIAgent CRD reconciliation contract before implementing the operator

- **Status:** To be implemented
- **Target:** v1
- **Date:** 2026-08-11
- **Decision owners:** Zuno Demo architecture team
- **Refines:** [ADR-0026](0026-provide-an-aiagent-kubernetes-crd-and-operator.md)

## Context

ADR-0026 proposes an `AIAgent` Kubernetes CRD and operator for v1, but intentionally deferred implementation while Tekos was the only functional vertical slice. ADR-0326 now expands the platform to four additional agents, which creates enough repeated lifecycle behavior to justify a controller if the reconciliation boundary is kept narrow.

Without a precise contract, an operator could accidentally duplicate Argo CD, embed OKF business behavior in a CRD, own shared platform services, or become a privileged controller that weakens existing namespace/identity boundaries.

The operator must automate **agent-instance lifecycle**, while Git remains the source of desired state, OKF remains the source of agent behavior, and shared platform components remain independently managed.

## Decision

Implement ADR-0026 only after defining and validating a narrow `AIAgent` reconciliation contract.

### Ownership model

```text
Git / Argo CD
   |
   +--> shared platform Applications
   |
   +--> AIAgent custom resources
              |
              v
         AIAgent Operator
              |
              +--> agent-specific frontend Deployment/Service/Route
              +--> agent-specific BFF Deployment/Service/config
              +--> OKF bundle ConfigMap/reference and runtime binding
              +--> agent-specific NetworkPolicy / ServiceAccount / RBAC bindings
              +--> optional agent-specific tool/RAG binding objects
              +--> status/conditions

Shared Agent Runtime / AI Gateway / RAG / MCP Gateway / Keycloak / PostgreSQL
remain independently lifecycle-managed platform services.
```

### CRD contract

The initial API should be versioned as an alpha contract, for example `zuno.ai/v1alpha1`, and represent deployment bindings rather than duplicating the OKF behavioral schema.

The spec should contain references or selectors for concepts such as:

- agent name and namespace intent;
- OKF bundle/source reference;
- frontend/BFF deployment profile and image references;
- entitlement/business-role group bindings;
- logical RAG collections;
- logical MCP/tool bindings;
- model-policy/profile reference;
- exposure/route settings;
- observability/evaluation profile.

Secrets, prompts, document bodies, OAuth refresh tokens and raw credentials must **not** be embedded in the CR. Secret material is referenced through the existing Vault/External Secrets pattern.

### Reconciliation boundary

The operator must **not**:

- install OpenShift AI, Keycloak, PostgreSQL, Vault, MaaS or other shared operators/services;
- become the source of truth for OKF task semantics;
- bypass Argo CD for the `AIAgent` CR itself;
- dynamically broaden cluster-level RBAC based on agent content;
- create unrestricted database credentials or model-provider credentials.

### Status contract

`status.conditions` must expose at least configuration validity, OKF readiness, frontend readiness, BFF readiness and runtime-binding readiness. The controller should surface reconciliation errors without hiding underlying Kubernetes conditions/events.

## Consequences

Adding an agent becomes a higher-level declarative operation while preserving the existing separation between behavioral definition, GitOps desired state and shared platform lifecycle.

The operator adds controller code, CRD versioning and upgrade responsibilities, so it should only be implemented after ADR-0326 proves which fields are genuinely common across at least two functional agents.

## Security considerations

The controller should be namespace-scoped or use the minimum cluster permissions required for multi-namespace reconciliation. Reconciled workloads must continue to satisfy restricted security, NetworkPolicy, trusted identity and secret-management ADRs.

The operator must validate namespace and reference boundaries so an `AIAgent` CR cannot reference another agent's secrets/configuration or gain arbitrary cluster resources.

## Operational considerations

Operator reconciliation must be idempotent and observable. Argo CD owns the `AIAgent` desired-state object; the operator owns only the generated agent-instance resources, avoiding an Argo/operator ownership fight over the same child manifests.

A conversion/versioning strategy is required before the API moves beyond `v1alpha1`.

## Acceptance criteria

- The CRD schema is validated against at least Tekos plus Arkos or Comage before implementation is declared complete.
- Creating an `AIAgent` CR through GitOps produces the expected per-agent frontend/BFF/configuration resources without modifying shared platform services.
- Deleting/suspending an `AIAgent` has a defined, safe lifecycle that does not delete shared data or secrets unexpectedly.
- Cross-namespace references and inline secret material are rejected.
- `status.conditions` provides useful readiness/error state consumed by `make check`.
- Existing plain-manifest agents can be migrated incrementally without a flag day.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0005](0005-use-okf-v0-2-as-the-declarative-agent-definition-contract.md)
- [ADR-0007](0007-separate-agent-instances-from-reusable-platform-components.md)
- [ADR-0008](0008-use-one-frontend-and-one-bff-deployment-per-agent.md)
- [ADR-0022](0022-use-gitops-managed-declarative-agent-tasks-and-policies.md)
- [ADR-0023](0023-use-a-namespace-per-agent-isolation-model.md)
- [ADR-0024](0024-use-vault-for-application-secrets.md)
- [ADR-0026](0026-provide-an-aiagent-kubernetes-crd-and-operator.md)
- [ADR-0038](0038-use-standards-compliant-okf-v0-2-markdown-bundles.md)
- [ADR-0039](0039-make-agent-runtime-execute-the-okf-agent-contract.md)
- [ADR-0052](0052-harden-all-workloads-for-openshift-restricted-security-and-secnumcloud-objectives.md)
- [ADR-0326](0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md)
