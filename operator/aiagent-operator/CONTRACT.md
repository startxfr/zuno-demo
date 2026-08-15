# AIAgent reconciliation contract

ADR-0327's ownership model, CRD contract, reconciliation boundary and
status contract, restated here as the operator's own working reference
(the ADR itself remains the source of truth; this file must not drift
from it - `validate_contract.py`'s `schema`/`reject_rules` checks are the
enforcement mechanism for the parts of this contract that are
machine-checkable today).

## Ownership model

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
              +--> agent-specific NetworkPolicy / ServiceAccount / RBAC
              +--> optional agent-specific tool/RAG binding objects
              +--> status/conditions

Shared Agent Runtime / AI Gateway / RAG / MCP Gateway / Keycloak /
PostgreSQL remain independently lifecycle-managed platform services.
```

Argo CD owns the `AIAgent` CR itself (desired state, in Git). The operator
owns only the resources it generates from that CR. This is a strict
split: neither side ever writes into the other's owned objects, avoiding
an Argo/operator ownership fight over the same child manifests.

## What the spec is (and is not)

`AIAgentSpec` (`api/v1alpha1/aiagent_types.go`) is deployment bindings and
references only: agent name/namespace intent, an OKF bundle Git-path
reference, frontend/BFF image + deployment-shape references, entitlement/
business-role Keycloak group bindings, logical RAG knowledge-domain ids,
logical MCP/tool capability ids, a model-policy reference, and an
evaluation-profile reference.

It is never:

- the source of OKF task/prompt/behavioral content (that stays in Git
  under `agents/<name>/`, referenced by `okfBundleRef`, never mirrored);
- a place for secrets, prompts, document bodies, OAuth refresh tokens or
  raw credentials (those resolve through the existing Vault/External
  Secrets pattern, by convention keyed off `agentName` - never carried by
  this CR at all);
- a way to reach outside `spec.targetNamespace` (no other field on the
  spec is namespace-shaped, so there is no field to point cross-namespace
  with in the first place).

## Reconciliation boundary - the operator must NOT

- install OpenShift AI, Keycloak, PostgreSQL, Vault, MaaS or other shared
  operators/services;
- become the source of truth for OKF task semantics;
- bypass Argo CD for the `AIAgent` CR itself;
- dynamically broaden cluster-level RBAC based on agent content;
- create unrestricted database credentials or model-provider credentials.

## Status contract

`status.conditions` must expose at least these five types (defined as
constants in `api/v1alpha1/aiagent_types.go`, so WP-38's controller and
any consumer share one name):

| Constant                       | `type` value           | Meaning                                    |
|---------------------------------|------------------------|---------------------------------------------|
| `ConditionConfigValid`          | `ConfigValid`           | The CR's own spec passed validation.        |
| `ConditionOKFReady`             | `OKFReady`               | `okfBundleRef` resolves to a valid bundle.  |
| `ConditionFrontendReady`        | `FrontendReady`          | Frontend Deployment/Service/Route healthy.  |
| `ConditionBFFReady`             | `BFFReady`               | BFF Deployment/Service healthy.             |
| `ConditionRuntimeBindingReady`  | `RuntimeBindingReady`    | RAG/MCP/model-policy bindings resolve.      |

The controller may add more condition types but must never drop any of
these five. Reconciliation errors surface as condition messages, not by
hiding underlying Kubernetes conditions/events.

## Incremental migration path

Plain-manifest agents (Tekos, Arkos, Comage, Advantage, Finage today, each
deployed via its own `gitops/apps/<agent>/application-d1.yaml` +
`gitops/charts/<agent>/`) migrate to CR-managed one at a time:

1. Author that agent's `AIAgent` CR (see `config/samples/` for the three
   already hand-derived from real chart values) and add it to GitOps.
2. Once WP-38's controller reconciles it and its resources reach Ready,
   remove the now-redundant plain-manifest Application/chart entry for
   *that agent only* - documented as an explicit diff in the migrating
   commit.
3. Every other agent's plain-manifest deployment is untouched. There is
   no flag day: plain-manifest and CR-managed agents coexist
   indefinitely, side by side, in the same `zuno-ai-run` namespace.

WP-38's plan designates Arkos as the first migration proof; Tekos stays
plain-manifest deliberately, to prove coexistence rather than a full cutover.

## Validation

`validate_contract.py` is the static half of this contract (schema shape,
secret/cross-namespace reject rules, chart/OKF drift). The dynamic half -
actually reconciling a CR into live resources with correct owner
references, RBAC scoped to per-agent kinds, and a real delete/suspend
lifecycle - is WP-38's controller plus its envtest suite.
