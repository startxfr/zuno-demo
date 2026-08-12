# ADR-0329: Consolidate agent workloads into the shared zuno-ai-run namespace

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-12
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0023](0023-use-a-namespace-per-agent-isolation-model.md) for agent workload namespace placement

## Decision

Retire the namespace-per-agent isolation model. Every active agent's
frontend and BFF deploy into the single shared `zuno-ai-run` namespace
(`gitops/charts/tekos`) instead of a dedicated `zuno-agent-<name>`
namespace, alongside the Agent Runtime, AI Gateway and MCP Gateway it
already hosted.

**Rationale:** `zuno-ai-run` was already documented as "shared runtime
hosting every active agent" (`gitops/charts/namespaces/values.yaml`)
before this ADR. A dedicated `zuno-agent-<name>` namespace per agent
duplicated that boundary without adding real isolation, since every
agent's FE/BFF already relied on precise, per-workload NetworkPolicies
(ADR-0037) rather than the coarser namespace boundary itself. Collapsing
the two removes four permanently-empty placeholder namespaces
(`zuno-agent-comage/advantage/finage/arkos`) and one now-redundant active
one (`zuno-agent-tekos`), each of which required its own quota,
default-deny baseline and RBAC surface for no functional isolation
benefit over the workload-level NetworkPolicies already in place.

**Implementation status (2026-08-12):** `gitops/charts/namespaces` no
longer creates or quotas any `zuno-agent-*` namespace (its `namespaces:`
values key, `templates/quota.yaml` and `templates/networkpolicy.yaml` were
removed); `gitops/charts/tekos` deploys into `zuno-ai-run`
(`values.yaml`'s `namespace`). The NetworkPolicies that used to cross the
`zuno-agent-tekos`/`zuno-ai-run` boundary
(`gitops/charts/agent-runtime/templates/networkpolicy.yaml`,
`gitops/charts/tekos/templates/networkpolicy.yaml`,
`gitops/charts/redis/templates/networkpolicy.yaml`) were updated to
same-namespace `podSelector` rules or to target `zuno-ai-run` by name. The
Day 1 build image-puller RoleBinding grant
(`ansible/tasks/apply_openshift_build.yml`) and the Keycloak realm's
per-client `agent.namespace` metadata
(`gitops/charts/keycloak/files/realm-zuno.json`) were updated to match.
Placeholder agents (Comage, Advantage, Finage, Arkos) now have no
dedicated namespace at all - only their `agent.okf.md` bundle exists
until a future FE/BFF chart deploys into `zuno-ai-run` for them.

## Security considerations

Isolation between agents was never actually provided by the namespace
boundary alone: `gitops/charts/agent-runtime`'s and `gitops/charts/tekos`'s
NetworkPolicies already scoped ingress to precise pod selectors
(ADR-0037), not "same namespace". Collapsing the namespace does not widen
any existing ingress rule - it removes a redundant boundary, not an
enforced one. A future agent that needs stronger tenant isolation than a
shared namespace provides remains free to introduce a dedicated
namespace, justified by that agent's own requirements, following the same
"dedicated namespaces are only introduced where required" convention
ADR-0328 states for OpenShift AI components.

See [Standard clauses](README.md#standard-clauses) for Context,
Alternatives, Consequences, Operational considerations, Migration/evolution
and Related ADRs.

## Related ADRs

- [ADR-0023](0023-use-a-namespace-per-agent-isolation-model.md) - superseded by this ADR for agent workload namespace placement
- [ADR-0007](0007-separate-agent-instances-from-reusable-platform-components.md) - Separate agent instances from reusable platform components
- [ADR-0031](0031-formalize-tekos-as-the-v0-vertical-slice.md) - Formalize Tekos as the v0 vertical slice
- [ADR-0037](0037-protect-mcp-servers-with-network-and-workload-identity-boundaries.md) - Protect MCP servers with network and workload identity boundaries
- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md) - Restructure deployment into Day 0 / Day 1 sequencing
- [ADR-0328](0328-separate-the-openshift-ai-control-plane-from-ai-build-and-run-workload-namespaces.md) - Separate the OpenShift AI control plane from AI build and run workload namespaces
