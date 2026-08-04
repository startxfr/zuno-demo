# Platform vs. agent instance separation

This note makes ADR-0007 concrete: which pieces of the Zuno agent platform
are **built once** and shared across every agent, and which pieces are
**instantiated per agent** through declarative configuration. It also
explains what that split means for a v0 demo where only one of five agents
is actually running.

## Shared platform (built once, reused by every agent)

These components have no agent-specific code path. An agent is a
configuration they consume, not a fork of them.

| Component | Responsibility | Owning ADR(s) |
|---|---|---|
| Agent Runtime | Task orchestration, conversation state, LangChain/LangGraph workflows, RAG and MCP invocation | ADR-0009, ADR-0018 |
| AI/Inference Gateway | Model selection/routing, quotas, cost, fallback, streaming, C1/C2/C3-aware provider choice | ADR-0009, ADR-0020, ADR-0021 |
| MCP Gateway + MCP tool servers | The single integration contract for tools (Confluence, Google Workspace, sales DB, web search) | ADR-0010, ADR-0011, ADR-0017 |
| Keycloak | Central identity provider; realm `zuno`, per-agent groups and OIDC clients | ADR-0012, ADR-0013 |
| Vault + External Secrets Operator | Application secret storage and in-cluster consumption | ADR-0024 |
| PostgreSQL + pgvector | Persistent data platform, RAG vector store, per-agent logically isolated schemas | ADR-0015, ADR-0016 |

A sixth agent should be addable "mainly by adding a declarative definition
and configuration" (MEMORY.md section 4) precisely because none of the above
needs to change to onboard it.

## Per-agent instance (declarative config, instantiated per agent)

Each agent is the same four ingredients, filled in differently:

1. **OKF definition** - `agents/<name>/agent.okf.yaml`, conforming to
   `platform/okf/schema/zuno-okf-v0.2.schema.json` (ADR-0005, ADR-0006).
   Declares the agent's tasks, allowed tools, model/classification hint,
   authorized Keycloak group(s) and portal UI metadata.
2. **Namespace** - `zuno-<name>`, with `zuno.io/agent` and `zuno.io/status`
   labels, dedicated service account(s), quotas and NetworkPolicies
   (ADR-0023). Created by the `gitops/charts/namespaces` chart for all five
   agents regardless of whether the agent is active.
3. **FE + BFF deployment** - one frontend and one BFF `Deployment` (plain
   Kubernetes, not the AIAgent CRD - see "Why not the AIAgent CRD" below),
   built from the shared `components/agent-frontend` and `components/agent-bff`
   codebases and parameterized per agent (ADR-0008). Only applied for agents
   with `status: active`.
4. **Keycloak group + OIDC client** - one realm group (`consultant`,
   `sales`, `adv`, `finance`, `board`) mapped to one OIDC client
   (`<name>-frontend`), owned by the identity track.

## What v0 actually runs

Of the five agents, **only Tekos has all four ingredients present and
live**: `status: active` in its OKF file, a populated `zuno-agent-tekos`
namespace, and a running FE + BFF `Deployment`/`Service`/`Route`
(`gitops/charts/tekos`).

Comage, Advantage, Finage and Arkos each have ingredients 1 and 2 only:

- an `agent.okf.yaml` with `status: placeholder`, a single `coming-soon`
  task with an empty tool list, and real `access.groups` / `ui` metadata so
  the portal can render an honest, access-gated tile;
- a reserved, labeled, empty `zuno-<name>` namespace, so the namespace-per-agent
  isolation model (ADR-0023) is demonstrably real infrastructure and not
  just a diagram - a reviewer can `oc get ns -l zuno.io/agent` and see all
  five agent boundaries already exist.

They have **no** FE/BFF `Deployment` and no Keycloak OIDC client wired up.
This is not a partial or broken build of those four agents - it is the
correct v0 shape for something that is, by design, declarative-config-only
until a later track flips its OKF `status` to `active` and a FE/BFF chart
is added for it. The portal (`components/agent-frontend`) reads
`spec.access.groups` from every `agent.okf.yaml` at startup and renders a
disabled "coming soon" tile for any agent whose OKF `status` is not
`active`, independent of whether the viewer's JWT groups would otherwise
grant access - so a sales user sees a gated Comage tile, not a broken link.

## Why not the AIAgent CRD (ADR-0026, retargeted to v1)

ADR-0026 originally proposed reconciling agent instances through a custom
`AIAgent` CRD and operator. With a single functional agent in v0, a
controller earns no reconciliation complexity it would actually exercise:
a plain `Deployment` + `Service` + `Route`, applied by ArgoCD from
`gitops/charts/tekos`, gives the same declarative-and-reviewable property
(GitOps-managed, PR-reviewed, no imperative `kubectl apply` by an operator)
at a fraction of the cost. The CRD/operator remains the intended v1
evolution once the platform hosts enough agents that hand-writing each
one's Deployment/Service/Route stops being cheaper than reconciliation
logic.
